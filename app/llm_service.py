"""LLM Service GEOSAT (SRS-FR-08).

Qwen API diakses via OpenAI SDK (compatible mode) dengan function calling.
LLM HANYA bertugas ekstraksi intent dan nama kapal dari pesan user.
LLM DILARANG menghasilkan data posisi/cuaca/sensor — semua nilai faktual
selalu diambil dari database/Open-Meteo di sisi orkestrator (app/main.py).
"""
import json
import logging
from typing import Any, Optional

from openai import OpenAI

from app.config import get_settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "Anda adalah modul ekstraksi intent untuk chatbot pelaporan kapal GEOSAT. "
    "Tugas Anda HANYA mengklasifikasikan pesan user ke salah satu fungsi yang tersedia "
    "dan mengekstrak nama kapal jika disebut. "
    "JANGAN pernah mengarang, menebak, atau menghasilkan data posisi, cuaca, atau sensor. "
    "Jika pesan tidak terkait informasi kapal (posisi/cuaca/sensor), panggil handle_unsupported. "
    "Jika nama kapal tidak disebut atau tidak yakin, biarkan argumen ship_name kosong."
)

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_ship_position",
            "description": "User meminta posisi/lokasi/koordinat/kecepatan/haluan kapal.",
            "parameters": {
                "type": "object",
                "properties": {
                    "ship_name": {
                        "type": "string",
                        "description": "Nama kapal yang disebut user (apa adanya, tanpa mengubah ejaan). Kosongkan jika tidak disebut.",
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_ship_weather",
            "description": "User meminta informasi cuaca di sekitar/lokasi kapal (angin, suhu, kondisi laut).",
            "parameters": {
                "type": "object",
                "properties": {
                    "ship_name": {
                        "type": "string",
                        "description": "Nama kapal yang disebut user (apa adanya). Kosongkan jika tidak disebut.",
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_ship_sensor",
            "description": "User meminta data sensor kapal (RPM mesin, BBM/bahan bakar, suhu mesin, tegangan, arus).",
            "parameters": {
                "type": "object",
                "properties": {
                    "ship_name": {
                        "type": "string",
                        "description": "Nama kapal yang disebut user (apa adanya). Kosongkan jika tidak disebut.",
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "handle_unsupported",
            "description": "Pesan tidak terkait informasi kapal, tidak jelas, atau di luar kemampuan sistem.",
            "parameters": {
                "type": "object",
                "properties": {
                    "reason": {
                        "type": "string",
                        "description": "Alasan singkat mengapa pesan tidak dapat dilayani.",
                    }
                },
                "required": ["reason"],
            },
        },
    },
]

VALID_INTENTS = {"get_ship_position", "get_ship_weather", "get_ship_sensor", "handle_unsupported"}


def _client() -> OpenAI:
    s = get_settings()
    return OpenAI(api_key=s.QWEN_API_KEY, base_url=s.QWEN_BASE_URL)


def classify_intent(message: str, ship_names: Optional[list[str]] = None) -> dict[str, Any]:
    """Klasifikasi pesan user -> {"name": <intent>, "arguments": {...}}.

    `ship_names` (daftar kapal milik user) disertakan di prompt hanya sebagai
    bantuan pencocokan nama; LLM tetap tidak diberi data faktual apa pun.
    Jika LLM gagal/error, fallback ke handle_unsupported (fail-safe).
    """
    s = get_settings()

    user_prompt = message
    if ship_names:
        user_prompt = (
            f"Daftar kapal milik user: {', '.join(ship_names)}\n"
            f"Pesan user: {message}"
        )

    try:
        resp = _client().chat.completions.create(
            model=s.QWEN_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            tools=TOOLS,
            tool_choice="required",
            temperature=0,
        )
    except Exception:
        logger.exception("Qwen API call failed; falling back to handle_unsupported")
        return {"name": "handle_unsupported", "arguments": {"reason": "llm_error"}}

    tool_calls = getattr(resp.choices[0].message, "tool_calls", None) or []
    if not tool_calls:
        return {"name": "handle_unsupported", "arguments": {"reason": "no_tool_call"}}

    fn = tool_calls[0].function
    if fn.name not in VALID_INTENTS:
        return {"name": "handle_unsupported", "arguments": {"reason": f"unknown_intent:{fn.name}"}}

    try:
        arguments = json.loads(fn.arguments or "{}")
    except json.JSONDecodeError:
        logger.warning("LLM returned invalid JSON arguments: %r", fn.arguments)
        arguments = {}

    ship_name = str(arguments.get("ship_name") or "").strip()
    return {"name": fn.name, "arguments": {"ship_name": ship_name} if fn.name != "handle_unsupported" else arguments}
