"""Database layer GEOSAT (PyMySQL).

Semua query dikembalikan sebagai dict. Koneksi dibuat per-call
(cocok untuk workload webhook yang pendek); kredensial dibaca
dari app.config (SRS-NFR-02).
"""
import json
import re
from typing import Any, Optional

import pymysql
from pymysql.cursors import DictCursor

from app.config import get_settings
from app.utils import mask_number


def get_connection() -> pymysql.connections.Connection:
    s = get_settings()
    return pymysql.connect(
        host=s.MYSQL_HOST,
        port=s.MYSQL_PORT,
        user=s.MYSQL_USER,
        password=s.MYSQL_PASSWORD,
        database=s.MYSQL_DB,
        charset="utf8mb4",
        cursorclass=DictCursor,
        autocommit=True,
    )


# ------------------------------------------------------------
# User & kapal (UC-01: validasi user terdaftar)
# ------------------------------------------------------------

def get_user_and_ships(phone: str) -> Optional[dict[str, Any]]:
    """Ambil user beserta daftar kapalnya. Return None jika tidak terdaftar."""
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT id, phone_number, name FROM users WHERE phone_number = %s",
            (phone,),
        )
        user = cur.fetchone()
        if not user:
            return None
        cur.execute(
            "SELECT id, ship_name, call_sign FROM ships WHERE user_id = %s ORDER BY ship_name",
            (user["id"],),
        )
        user["ships"] = cur.fetchall()
        return user


# ------------------------------------------------------------
# Pencocokan nama kapal (case-insensitive, abaikan prefix 'KM')
# ------------------------------------------------------------

def _normalize_ship_name(name: str) -> str:
    """'KM Bahari Jaya' -> 'bahari jaya' (lowercase, tanpa prefix KM/MV, spasi dirapikan)."""
    n = re.sub(r"\s+", " ", (name or "").strip().lower())
    n = re.sub(r"^(km|k\.m\.|mv|tb|kt)\s+", "", n)
    return n.strip()


def match_ship(ships: list[dict[str, Any]], text: str) -> Optional[dict[str, Any]]:
    """Cari kapal yang namanya disebut di text.

    - Case-insensitive, prefix 'KM' diabaikan di kedua sisi.
    - Prioritas: kecocokan nama penuh lebih dulu, lalu kecocokan sebagian
      (nama kapal disebut di text, atau text menyebut potongan nama kapal).
    - Return None jika tidak ada / ambigu (lebih dari satu kecocokan).
    """
    text_norm = _normalize_ship_name(text)
    if not text_norm or not ships:
        return None

    full_matches, partial_matches = [], []
    for ship in ships:
        name_norm = _normalize_ship_name(ship["ship_name"])
        if not name_norm:
            continue
        if name_norm == text_norm:
            full_matches.append(ship)
        else:
            # Kecocokan sebagian berbasis batas kata, bukan substring mentah,
            # agar 'km' tidak ikut cocok dengan 'makmur'.
            name_in_text = re.search(rf"\b{re.escape(name_norm)}\b", text_norm)
            text_in_name = re.search(rf"\b{re.escape(text_norm)}\b", name_norm)
            if name_in_text or text_in_name:
                partial_matches.append(ship)

    if len(full_matches) == 1:
        return full_matches[0]
    if not full_matches and len(partial_matches) == 1:
        return partial_matches[0]
    return None


# ------------------------------------------------------------
# Posisi & sensor (ambil baris terbaru per kapal)
# ------------------------------------------------------------

def get_position(ship_id: int) -> Optional[dict[str, Any]]:
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT latitude, longitude, speed_knots, heading, reported_at
            FROM ship_positions
            WHERE ship_id = %s
            ORDER BY reported_at DESC
            LIMIT 1
            """,
            (ship_id,),
        )
        return cur.fetchone()


def get_sensor(ship_id: int) -> Optional[dict[str, Any]]:
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT rpm_engine_1, rpm_engine_2, fuel_level_l, fuel_capacity_l,
                   engine_temp_c, device_temp_c, voltage_v, current_a, recorded_at
            FROM ship_sensors
            WHERE ship_id = %s
            ORDER BY recorded_at DESC
            LIMIT 1
            """,
            (ship_id,),
        )
        return cur.fetchone()


# ------------------------------------------------------------
# Konteks percakapan (TTL 15 menit, SRS 6.2)
# ------------------------------------------------------------

def save_context(phone: str, pending_intent: Optional[str], pending_payload: Optional[dict] = None) -> None:
    """Upsert konteks. pending_intent=None berarti hapal konteks (selesai)."""
    with get_connection() as conn, conn.cursor() as cur:
        if pending_intent is None:
            cur.execute("DELETE FROM chat_contexts WHERE phone_number = %s", (phone,))
        else:
            cur.execute(
                """
                INSERT INTO chat_contexts (phone_number, pending_intent, pending_payload)
                VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    pending_intent = VALUES(pending_intent),
                    pending_payload = VALUES(pending_payload),
                    updated_at = CURRENT_TIMESTAMP
                """,
                (phone, pending_intent, json.dumps(pending_payload) if pending_payload else None),
            )


def get_context(phone: str) -> Optional[dict[str, Any]]:
    """Ambil konteks yang masih berlaku (diupdate dalam CONTEXT_TTL_MINUTES terakhir)."""
    ttl = get_settings().CONTEXT_TTL_MINUTES
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT pending_intent, pending_payload, updated_at
            FROM chat_contexts
            WHERE phone_number = %s
              AND updated_at >= (NOW() - INTERVAL %s MINUTE)
            """,
            (phone, ttl),
        )
        ctx = cur.fetchone()
    if ctx and ctx.get("pending_payload"):
        try:
            ctx["pending_payload"] = json.loads(ctx["pending_payload"])
        except (TypeError, ValueError):
            ctx["pending_payload"] = None
    return ctx


# ------------------------------------------------------------
# Log permintaan (SRS-FR-24, nomor tersamarkan)
# ------------------------------------------------------------

def save_log(
    phone: str,
    message_in: str,
    intent: Optional[str] = None,
    ship_name: Optional[str] = None,
    message_out: Optional[str] = None,
    status: str = "success",
) -> None:
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO request_logs (phone_masked, message_in, intent, ship_name, message_out, status)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (mask_number(phone), message_in, intent, ship_name, message_out, status),
        )
