"""Fungsi utilitas GEOSAT.

Aturan format SRS 3.1:
- Waktu WAJIB format WIB, contoh: "25 Okt 2026 14:05 WIB".
- Desimal WAJIB pakai koma (7,5), KECUALI koordinat dan link maps.
- Nomor WA di log WAJIB tersamarkan (SRS-FR-24), contoh: 6281*****123.
"""
import hashlib
import hmac
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Union

# WIB = UTC+7, tanpa DST -> offset tetap aman tanpa tzdata.
WIB = timezone(timedelta(hours=7), name="WIB")

MONTHS_ID = [
    "Jan", "Feb", "Mar", "Apr", "Mei", "Jun",
    "Jul", "Agu", "Sep", "Okt", "Nov", "Des",
]


def format_date_wib(dt: Union[datetime, None]) -> str:
    """Format datetime ke '25 Okt 2026 14:05 WIB'.

    - datetime naive dianggap sudah dalam WIB.
    - datetime aware dikonversi ke WIB.
    """
    if dt is None:
        return "-"
    if dt.tzinfo is None:
        dt_wib = dt.replace(tzinfo=WIB)
    else:
        dt_wib = dt.astimezone(WIB)
    return (
        f"{dt_wib.day:02d} {MONTHS_ID[dt_wib.month - 1]} {dt_wib.year} "
        f"{dt_wib.hour:02d}:{dt_wib.minute:02d} WIB"
    )


def format_decimal_id(value: Union[float, Decimal, int, str, None], digits: int = 1) -> str:
    """Ubah desimal ke format Indonesia (titik -> koma), contoh 7.5 -> '7,5'.

    TIDAK dipakai untuk koordinat/link maps (SRS 3.1 mewajibkan titik di sana).
    """
    if value is None:
        return "-"
    d = Decimal(str(value)).quantize(Decimal(1).scaleb(-digits))
    return str(d).replace(".", ",")


def mask_number(phone: str) -> str:
    """Samarkan nomor WA untuk log: 6281234567890 -> 6281*****123."""
    phone = (phone or "").strip()
    if len(phone) <= 7:
        return "*****"
    return f"{phone[:4]}*****{phone[-3:]}"


def verify_webhook_signature(payload_body: bytes, signature_header: str, app_secret: str) -> bool:
    """Verifikasi X-Hub-Signature-256 dari Meta (SRS-FR-01).

    Header berbentuk 'sha256=<hex digest>' dari HMAC-SHA256 body dengan app secret.
    """
    if not signature_header or not app_secret:
        return False
    expected = "sha256=" + hmac.new(
        app_secret.encode("utf-8"), payload_body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature_header)
