from fastapi import FastAPI, Request, HTTPException, Header
import httpx
from app.config import settings
from app import db, llm_service
from app.utils import format_date_wib, mask_number, verify_webhook_signature

app = FastAPI()

async def send_wa_message(to: str, text: str):
    url = f"https://graph.facebook.com/v19.0/{settings.WA_PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {settings.WA_TOKEN}", "Content-Type": "application/json"}
    payload = {"messaging_product": "whatsapp", "to": to, "type": "text", "text": {"body": text}}
    async with httpx.AsyncClient() as client:
        await client.post(url, json=payload, headers=headers)

@app.get("/webhook")
async def verify_webhook(hub_mode: str, hub_verify_token: str, hub_challenge: str):
    if hub_mode == "subscribe" and hub_verify_token == settings.WA_VERIFY_TOKEN:
        return int(hub_challenge)
    raise HTTPException(status_code=403, detail="Forbidden")

@app.post("/webhook")
async def webhook(request: Request, x_hub_signature_256: str = Header(None)):
    raw_body = await request.body()
    body_str = raw_body.decode('utf-8')
    
    # SRS-FR-01: Verifikasi Tanda Tangan
    if not verify_webhook_signature(body_str, x_hub_signature_256, settings.WA_APP_SECRET):
        raise HTTPException(status_code=403, detail="Invalid signature")

    body = await request.json()
    try:
        changes = body['entry'][0]['changes'][0]['value']
        if 'messages' not in changes: return {"status": "ignored"}
        
        msg = changes['messages'][0]
        if msg['type'] != 'text':
            await send_wa_message(msg['from'], "Maaf, sistem hanya mendukung pesan teks.")
            return {"status": "ok"}

        phone = msg['from']
        text = msg['text']['body']
    except Exception:
        return {"status": "error parsing"}

    # UC-01: Validasi User
    user, ships = db.get_user_and_ships(phone)
    if not user:
        await send_wa_message(phone, "Nomor belum terdaftar. Silakan hubungi GEOSAT.")
        return {"status": "ok"}
    if not ships:
        await send_wa_message(phone, "Belum ada kapal terhubung dengan akun Anda.")
        return {"status": "ok"}

    # Cek Konteks 15 Menit (SRS-FR-11) & UC-02
    ctx = db.get_context(user['id'])
    intent, args = "handle_unsupported", {"reason": "unclear"}
    
    if ctx and text.isdigit() and 1 <= int(text) <= len(ships):
        selected_ship = ships[int(text) - 1]
        intent = ctx['pending_intent'] or "get_ship_position"
        args = {"ship_name": selected_ship['full_name']}
    else:
        intent, args = llm_service.classify_intent(text, ships)

    ship_name_llm = args.get("ship_name", "")
    target_ship = db.match_ship(ships, ship_name_llm) if ship_name_llm else None

    if not target_ship and len(ships) > 1 and intent not in ["handle_unsupported", None]:
        ship_list = "\n".join([f"{i+1}. {s['full_name']}" for i, s in enumerate(ships)])
        db.save_context(user['id'], None, intent)
        reply = f"Anda memiliki {len(ships)} kapal. Pilih kapal:\n{ship_list}\n\nBalas dengan nomor kapal."
        await send_wa_message(phone, reply)
        return {"status": "ok"}
    
    if not target_ship and len(ships) == 1:
        target_ship = ships[0]

    # Eksekusi Intent & Format Respons (SRS 3.1)
    reply = ""
    if intent == "get_ship_position" and target_ship:
        pos = db.get_position(target_ship['id'])
        if pos:
            db.save_context(user['id'], target_ship['id'], "get_ship_position")
            tgl = format_date_wib(pos['reported_at'])
            maps_link = f"https://maps.google.com/?q={pos['latitude']},{pos['longitude']}"
            reply = (f"Posisi {target_ship['full_name']}\n"
                     f"Koordinat: {pos['latitude']}, {pos['longitude']}\n"
                     f"Kecepatan: {pos['speed_knots']} knot | Haluan: {pos['heading_degrees']}°\n"
                     f"Laporan terakhir: {tgl}\nPeta: {maps_link}")
        else: reply = "Posisi kapal belum tersedia."

    elif intent == "get_ship_weather" and target_ship:
        pos = db.get_position(target_ship['id'])
        if pos:
            url = f"https://api.open-meteo.com/v1/forecast?latitude={pos['latitude']}&longitude={pos['longitude']}&current=temperature_2m,wind_speed_10m,weather_code"
            async with httpx.AsyncClient() as client:
                weather_data = (await client.get(url)).json()
            curr = weather_data['current']
            db.save_context(user['id'], target_ship['id'], "get_ship_weather")
            reply = (f"Cuaca di sekitar {target_ship['full_name']}\n"
                     f"Kondisi: Kode {curr['weather_code']}\n"
                     f"Suhu udara: {curr['temperature_2m']} °C\n"
                     f"Angin: {curr['wind_speed_10m']} km/jam\n"
                     f"Sumber: Open-Meteo, prakiraan")
        else: reply = "Posisi kapal tidak ditemukan untuk cek cuaca."

    elif intent == "get_ship_sensor" and target_ship:
        sensor = db.get_sensor(target_ship['id'])
        if sensor:
            db.save_context(user['id'], target_ship['id'], "get_ship_sensor")
            tgl = format_date_wib(sensor['reported_at'])
            reply = (f"Data sensor {target_ship['full_name']}\n"
                     f"Waktu data: {tgl}\n"
                     f"RPM mesin 1: {sensor['rpm_engine1']}\n"
                     f"BBM: {sensor['fuel_liters']} L dari kapasitas {sensor['fuel_capacity']} L\n"
                     f"Suhu ruang mesin: {sensor['temp_engine']} °C\n"
                     f"Tegangan: {sensor['voltage']} V")
        else: reply = "Data sensor tidak tersedia untuk kapal tersebut."

    else:
        reply = "Halo! Saya dapat membantu informasi kapal Anda:\n1. Posisi kapal\n2. Cuaca\n3. Data sensor\n\nSilakan tulis pertanyaan, misal: posisi KM Bahari Jaya"

    await send_wa_message(phone, reply)
    return {"status": "ok"}