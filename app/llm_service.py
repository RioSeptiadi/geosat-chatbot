import json
from openai import OpenAI
from app.config import settings

client = OpenAI(api_key=settings.QWEN_API_KEY, base_url=settings.QWEN_BASE_URL)

tools = [
    {"type": "function", "function": {"name": "get_ship_position", "description": "Gunakan jika user menanyakan posisi, lokasi, koordinat, atau peta kapal.", "parameters": {"type": "object", "properties": {"ship_name": {"type": "string"}}, "required": ["ship_name"]}}},
    {"type": "function", "function": {"name": "get_ship_weather", "description": "Gunakan jika user menanyakan cuaca, ombak, gelombang, angin, atau suhu di sekitar kapal.", "parameters": {"type": "object", "properties": {"ship_name": {"type": "string"}}, "required": ["ship_name"]}}},
    {"type": "function", "function": {"name": "get_ship_sensor", "description": "Gunakan jika user menanyakan data sensor: BBM, bahan bakar, solar, RPM, mesin, suhu mesin, tegangan, aki, arus.", "parameters": {"type": "object", "properties": {"ship_name": {"type": "string"}}, "required": ["ship_name"]}}},
    {"type": "function", "function": {"name": "handle_unsupported", "description": "Gunakan jika user menyapa (halo, hai), bertanya di luar topik (tagihan, troubleshooting, bantuan), atau pesan tidak jelas.", "parameters": {"type": "object", "properties": {"reason": {"type": "string", "enum": ["greeting", "out_of_scope", "unclear"]}}, "required": ["reason"]}}}
]

def classify_intent(message: str, available_ships: list) -> tuple[str, dict]:
    ship_list_str = ", ".join([s['full_name'] for s in available_ships])
    system_prompt = f"""Kamu adalah asisten GEOSAT. Daftar kapal user: [{ship_list_str}].
Tentukan intent dan nama kapal. Jika user membalas angka, pilih kapal ke-angka tersebut. 
Jika tidak menyebut kapal, gunakan konteks sebelumnya atau kembalikan nama kosong."""

    try:
        response = client.chat.completions.create(
            model=settings.QWEN_MODEL,
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": message}],
            tools=tools, tool_choice="auto", temperature=0.1
        )
        msg = response.choices[0].message
        if msg.tool_calls and len(msg.tool_calls) > 0:
            tool_call = msg.tool_calls[0]
            args = json.loads(tool_call.function.arguments)
            return tool_call.function.name, args
        return "handle_unsupported", {"reason": "unclear"}
    except Exception as e:
        print(f"[LLM Error] {e}")
        return "handle_unsupported", {"reason": "llm_error"}