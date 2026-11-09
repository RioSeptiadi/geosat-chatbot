import hmac
import hashlib
from datetime import datetime, timedelta, timezone

def format_date_wib(dt: datetime):
    months = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"]
    # Asumsi dt dari DB adalah UTC, konversi ke WIB (UTC+7)
    wib_dt = dt.replace(tzinfo=timezone.utc) + timedelta(hours=7)
    return f"{wib_dt.day} {months[wib_dt.month-1]} {wib_dt.year} {wib_dt.strftime('%H:%M')} WIB"

def mask_number(phone: str):
    if len(phone) > 6:
        return phone[:4] + "*" * (len(phone) - 6) + phone[-2:]
    return phone

def verify_webhook_signature(payload: str, signature: str, app_secret: str) -> bool:
    expected_signature = hmac.new(
        app_secret.encode('utf-8'), 
        payload.encode('utf-8'), 
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected_signature, signature)