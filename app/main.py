"""GEOSAT WhatsApp Webhook - Orkestrator (SRS-FR-01, UC-01 s.d. UC-05).

Alur: webhook Meta -> verifikasi signature -> validasi user (UC-01)
-> konteks 15 menit / klasifikasi intent LLM -> disambiguasi kapal (UC-02)
-> eksekusi intent dari DB & Open-Meteo (UC-03/04/05) -> format SRS 3.1
-> kirim ke WhatsApp -> simpan log (SRS-FR-24).
"""
import json
import logging
from datetime import datetime
from typing import Any, Optional

import httpx
from fastapi import BackgroundTasks, FastAPI, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse

from app.config import get_settings
from app.db import (
    get_context,
    get_position,
    get_sensor,
    get_user_and_ships,
    match_ship,
    save_context,
    save_log,
)
from app.llm_service import classify_intent
from app.utils import WIB, format_date_wib, format_decimal_id, verify_webhook_signature

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("geosat")

app = FastAPI(title="GEOSAT WhatsApp Bot")


@app.get("/")
async def root() -> HTMLResponse:
    """Landing page sederhana (dipakai Meta untuk validasi website bisnis)."""
    return HTMLResponse(
        "<!DOCTYPE html>\n"
        '<html lang="id">\n'
        "<head>\n"
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        "<title>GEOSAT - Sistem Reporting Satelit Kapal</title>\n"
        "</head>\n"
        "<body>\n"
        "<h1>GEOSAT</h1>\n"
        "<p>Sistem Reporting Satelit Kapal Berbasis LLM Melalui WhatsApp.</p>\n"
        "</body>\n"
        "</html>"
    )

# ------------------------------------------------------------
# Template respons (SRS 3.1 - dipakai persis)
# ------------------------------------------------------------

TPL_POSITION = (
    "*Posisi {nama_kapal}*\n"
    "Koordinat: {lat}, {lon}\n"
    "Kecepatan: {speed} knot | Haluan: {heading}°\n"
    "Laporan terakhir: {time}\n"
    "Peta: https://maps.google.com/?q={lat},{lon}"
)

TPL_WEATHER = (
    "*Cuaca di sekitar {nama_kapal}*\n"
    "Kondisi: {code}\n"
    "Suhu udara: {temp} °C\n"
    "Angin: {wind} km/jam\n"
    "Sumber: Open-Meteo, {time} (prakiraan)"
)

TPL_SENSOR = (
    "*Data sensor {nama_kapal}*\n"
    "Waktu data: {time}\n"
    "RPM mesin 1: {rpm1} | RPM mesin 2: {rpm2}\n"
    "BBM: {fuel} L dari kapasitas {cap} L\n"
    "Suhu ruang mesin: {temp_eng} °C | Suhu perangkat: {temp_dev} °C\n"
    "Tegangan: {volt} V | Arus: {curr} A"
)

TPL_MENU = (
    "Halo! Saya dapat membantu informasi kapal Anda:\n"
    "1. Posisi kapal\n"
    "2. Cuaca di sekitar kapal\n"
    "3. Data sensor kapal\n"
    "\n"
    "Balas dengan nomor menu atau tulis pertanyaan, misalnya *posisi KM Bahari Jaya*."
)

MSG_UNREGISTERED = (
    "Maaf, nomor Anda belum terdaftar di sistem GEOSAT. "
    "Hubungi administrator untuk pendaftaran."
)

MSG_UNSUPPORTED = (
    "Maaf, saya hanya dapat membantu informasi kapal Anda "
    "(posisi, cuaca, dan data sensor).\n\n" + TPL_MENU
)

MSG_NO_POSITION = "Maaf, data posisi *{nama_kapal}* belum tersedia."

MSG_NO_SENSOR = "Maaf, data sensor *{nama_kapal}* saat ini tidak tersedia."

MSG_WEATHER_FAILED = (
    "Maaf, informasi cuaca untuk *{nama_kapal}* sedang tidak dapat diambil. "
    "Silakan coba lagi beberapa saat."
)

INTENT_BY_MENU_NUMBER = {
    "1": "get_ship_position",
    "2": "get_ship_weather",
    "3": "get_ship_sensor",
}

# Deskripsi kode cuaca WMO (Open-Meteo) dalam Bahasa Indonesia
WMO_CODES = {
    0: "Cerah", 1: "Cerah berawan", 2: "Berawan sebagian", 3: "Berawan",
    45: "Berkabut", 48: "Berkabut (embun beku)",
    51: "Gerimis ringan", 53: "Gerimis", 55: "Gerimis lebat",
    56: "Gerimis beku ringan", 57: "Gerimis beku",
    61: "Hujan ringan", 63: "Hujan sedang", 65: "Hujan lebat",
    66: "Hujan beku ringan", 67: "Hujan beku",
    71: "Salju ringan", 73: "Salju sedang", 75: "Salju lebat", 77: "Butiran salju",
    80: "Hujan singkat ringan", 81: "Hujan singkat", 82: "Hujan singkat lebat",
    85: "Salju singkat ringan", 86: "Salju singkat",
    95: "Badai petir", 96: "Badai petir dengan es ringan", 99: "Badai petir dengan es",
}


# ------------------------------------------------------------
# Pengirim pesan WhatsApp
# ------------------------------------------------------------

async def send_whatsapp(to_phone: str, text: str) -> None:
    s = get_settings()
    url = f"{s.WA_GRAPH_URL}/{s.WA_PHONE_NUMBER_ID}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "to": to_phone,
        "type": "text",
        "text": {"body": text},
    }
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                url, json=payload, headers={"Authorization": f"Bearer {s.WA_TOKEN}"}
            )
            if resp.status_code >= 400:
                logger.error("Gagal kirim WA (%s): %s", resp.status_code, resp.text)
    except httpx.HTTPError:
        logger.exception("HTTP error saat mengirim pesan WA")


# ------------------------------------------------------------
# Webhook endpoints (SRS-FR-01)
# ------------------------------------------------------------

@app.get("/webhook")
async def verify_webhook(
    hub_mode: str = Query("", alias="hub.mode"),
    hub_verify_token: str = Query("", alias="hub.verify_token"),
    hub_challenge: str = Query("", alias="hub.challenge"),
) -> PlainTextResponse:
    """Verifikasi webhook dari Meta (hub.mode=subscribe + verify token)."""
    s = get_settings()
    if hub_mode == "subscribe" and hub_verify_token == s.WA_VERIFY_TOKEN:
        return PlainTextResponse(hub_challenge)
    return PlainTextResponse("Forbidden", status_code=403)


@app.post("/webhook")
async def receive_webhook(request: Request, background: BackgroundTasks) -> JSONResponse:
    """Terima pesan masuk. WAJIB verifikasi X-Hub-Signature-256 sebelum diproses."""
    s = get_settings()
    body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256", "")

    if not verify_webhook_signature(body, signature, s.WA_APP_SECRET):
        logger.warning("Webhook signature tidak valid dari %s", request.client)
        return JSONResponse({"error": "invalid signature"}, status_code=401)

    try:
        payload = json.loads(body)
    except ValueError:
        return JSONResponse({"error": "invalid json"}, status_code=400)

    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            for message in value.get("messages", []):
                # Proses di background agar Meta langsung menerima 200 (hindari retry).
                background.add_task(handle_message, message)

    return JSONResponse({"status": "ok"})


# ------------------------------------------------------------
# Penanganan pesan (UC-01 s.d. UC-05)
# ------------------------------------------------------------

async def handle_message(message: dict[str, Any]) -> None:
    if message.get("type") != "text":
        phone = message.get("from", "")
        await send_whatsapp(phone, "Maaf, saat ini saya hanya dapat memproses pesan teks.\n\n" + TPL_MENU)
        return

    phone = message.get("from", "")
    text = (message.get("text", {}).get("body") or "").strip()
    if not phone or not text:
        return

    try:
        await process_message(phone, text)
    except Exception:
        logger.exception("Error memproses pesan dari %s", phone)
        save_log(phone, text, status="error")
        await send_whatsapp(phone, "Terjadi kesalahan pada sistem. Silakan coba lagi.")


async def process_message(phone: str, text: str) -> None:
    # ---- UC-01: validasi user terdaftar ----
    user = get_user_and_ships(phone)
    if not user:
        save_log(phone, text, status="unregistered")
        await send_whatsapp(phone, MSG_UNREGISTERED)
        return

    ships = user.get("ships", [])

    # ---- Konteks 15 menit: user sedang memilih kapal (UC-02) ----
    ctx = get_context(phone)
    if ctx and ctx.get("pending_intent"):
        picked = resolve_ship_choice(text, ships)
        if picked:
            save_context(phone, None)  # konteks selesai
            await execute_intent(phone, text, ctx["pending_intent"], picked, ships)
            return
        # Balasan bukan pilihan -> batalkan konteks, proses sebagai pesan baru.
        save_context(phone, None)

    # ---- Pesan menu / angka tanpa konteks ----
    if text.lower() in ("menu", "halo", "hallo", "hai", "hi", "start", "mulai"):
        save_log(phone, text, intent="menu")
        await send_whatsapp(phone, TPL_MENU)
        return

    if text in INTENT_BY_MENU_NUMBER:
        intent = INTENT_BY_MENU_NUMBER[text]
        if len(ships) == 1:
            await execute_intent(phone, text, intent, ships[0], ships)
        else:
            save_context(phone, intent)
            await send_whatsapp(phone, build_ship_picker(ships))
        return

    # ---- SRS-FR-08: LLM hanya untuk ekstraksi intent & nama kapal ----
    result = classify_intent(text, [s["ship_name"] for s in ships])
    intent = result["name"]
    llm_ship_name = result["arguments"].get("ship_name", "")

    if intent == "handle_unsupported":
        save_log(phone, text, intent="unsupported")
        await send_whatsapp(phone, MSG_UNSUPPORTED)
        return

    # ---- UC-02: disambiguasi kapal ----
    ship = match_ship(ships, llm_ship_name) if llm_ship_name else None
    if ship is None and len(ships) == 1:
        ship = ships[0]
    if ship is None:
        save_context(phone, intent)
        save_log(phone, text, intent=intent, status="pending_ship_choice")
        await send_whatsapp(phone, build_ship_picker(ships))
        return

    await execute_intent(phone, text, intent, ship, ships)


def resolve_ship_choice(text: str, ships: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    """User membalas angka 1..N atau nama kapal saat diminta memilih."""
    t = text.strip()
    if t.isdigit():
        idx = int(t)
        if 1 <= idx <= len(ships):
            return ships[idx - 1]
        return None
    return match_ship(ships, t)


def build_ship_picker(ships: list[dict[str, Any]]) -> str:
    lines = [f"{i}. {s['ship_name']}" for i, s in enumerate(ships, 1)]
    return (
        "Anda memiliki beberapa kapal. Balas dengan angka untuk memilih kapal:\n"
        + "\n".join(lines)
    )


# ------------------------------------------------------------
# Eksekusi intent (UC-03 posisi, UC-04 cuaca, UC-05 sensor)
# ------------------------------------------------------------

async def execute_intent(
    phone: str, text_in: str, intent: str, ship: dict[str, Any], ships: list[dict[str, Any]]
) -> None:
    ship_name = ship["ship_name"]
    ship_id = ship["id"]

    if intent == "get_ship_position":
        reply = build_position_reply(ship_id, ship_name)
    elif intent == "get_ship_weather":
        reply = await build_weather_reply(ship_id, ship_name)
    elif intent == "get_ship_sensor":
        reply = build_sensor_reply(ship_id, ship_name)
    else:
        reply = MSG_UNSUPPORTED

    save_log(phone, text_in, intent=intent, ship_name=ship_name, message_out=reply)
    await send_whatsapp(phone, reply)


def build_position_reply(ship_id: int, ship_name: str) -> str:
    pos = get_position(ship_id)
    if not pos:
        return MSG_NO_POSITION.format(nama_kapal=ship_name)
    # SRS 3.1: koordinat & link maps pakai TITIK; kecepatan pakai KOMA.
    lat = f"{float(pos['latitude']):.6f}"
    lon = f"{float(pos['longitude']):.6f}"
    return TPL_POSITION.format(
        nama_kapal=ship_name,
        lat=lat,
        lon=lon,
        speed=format_decimal_id(pos["speed_knots"], 1),
        heading=int(pos["heading"]),
        time=format_date_wib(pos["reported_at"]),
    )


async def build_weather_reply(ship_id: int, ship_name: str) -> str:
    pos = get_position(ship_id)
    if not pos:
        return MSG_NO_POSITION.format(nama_kapal=ship_name)

    s = get_settings()
    params = {
        "latitude": float(pos["latitude"]),
        "longitude": float(pos["longitude"]),
        "current": "weather_code,temperature_2m,wind_speed_10m",
        "timezone": "Asia/Jakarta",
    }
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(s.OPEN_METEO_URL, params=params)
            resp.raise_for_status()
            data = resp.json()
        current = data["current"]
    except (httpx.HTTPError, KeyError, ValueError):
        logger.exception("Gagal mengambil cuaca Open-Meteo untuk %s", ship_name)
        return MSG_WEATHER_FAILED.format(nama_kapal=ship_name)

    code = WMO_CODES.get(int(current["weather_code"]), f"Kode {current['weather_code']}")
    now_wib = datetime.now(WIB)
    return TPL_WEATHER.format(
        nama_kapal=ship_name,
        code=code,
        temp=format_decimal_id(current["temperature_2m"], 1),
        wind=format_decimal_id(current["wind_speed_10m"], 1),
        time=format_date_wib(now_wib),
    )


def build_sensor_reply(ship_id: int, ship_name: str) -> str:
    sensor = get_sensor(ship_id)
    if not sensor:
        return MSG_NO_SENSOR.format(nama_kapal=ship_name)

    rpm1, rpm2 = int(sensor["rpm_engine_1"]), int(sensor["rpm_engine_2"])
    # RPM 0 = sensor tidak mengirim nilai / kapal tanpa sensor aktif.
    if rpm1 == 0 and rpm2 == 0:
        return MSG_NO_SENSOR.format(nama_kapal=ship_name)

    return TPL_SENSOR.format(
        nama_kapal=ship_name,
        time=format_date_wib(sensor["recorded_at"]),
        rpm1=rpm1,
        rpm2=rpm2 if rpm2 != 0 else "-",
        fuel=int(sensor["fuel_level_l"]),
        cap=int(sensor["fuel_capacity_l"]),
        temp_eng=format_decimal_id(sensor["engine_temp_c"], 1),
        temp_dev=format_decimal_id(sensor["device_temp_c"], 1),
        volt=format_decimal_id(sensor["voltage_v"], 1),
        curr=format_decimal_id(sensor["current_a"], 1),
    )
