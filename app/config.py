"""Konfigurasi aplikasi GEOSAT.

SRS-NFR-02: seluruh kredensial WAJIB dibaca dari environment variable.
Tidak ada secret yang boleh di-hardcode di source code.
"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ===== Database MySQL (SRS 6.2) =====
    MYSQL_HOST: str = "localhost"
    MYSQL_USER: str
    MYSQL_PASSWORD: str
    MYSQL_DB: str = "mygeosat"
    MYSQL_PORT: int = 3306

    # ===== WhatsApp Cloud API (SRS-FR-01) =====
    WA_TOKEN: str
    WA_PHONE_NUMBER_ID: str
    WA_VERIFY_TOKEN: str
    WA_APP_SECRET: str

    # ===== Qwen API via OpenAI SDK (SRS-FR-08) =====
    QWEN_API_KEY: str
    QWEN_BASE_URL: str = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
    QWEN_MODEL: str = "qwen-plus"

    # ===== Parameter perilaku (bukan secret) =====
    CONTEXT_TTL_MINUTES: int = 15  # SRS 6.2: masa berlaku konteks percakapan
    OPEN_METEO_URL: str = "https://api.open-meteo.com/v1/forecast"
    WA_GRAPH_URL: str = "https://graph.facebook.com/v21.0"


@lru_cache
def get_settings() -> Settings:
    return Settings()
