import asyncio
import json
import re
from config import GEMINI_API_KEY, GEMINI_MODEL

try:
    from google import genai
    from google.genai import types
    _client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None
except Exception:  # kutubxona yoki kalit bo'lmasa
    _client = None
    types = None


class AIError(Exception):
    pass


async def ask(prompt, system=None, history=None, json_mode=False):
    """Gemini'dan javob oladi. history: [("user"|"model", matn), ...]"""
    if not _client:
        raise AIError("Gemini API kaliti sozlanmagan")
    contents = [{"role": r, "parts": [{"text": t}]} for r, t in (history or [])]
    contents.append({"role": "user", "parts": [{"text": prompt}]})
    cfg = types.GenerateContentConfig(
        system_instruction=system,
        response_mime_type="application/json" if json_mode else None,
        temperature=0.6)
    last = None
    for attempt in range(3):
        try:
            r = await _client.aio.models.generate_content(model=GEMINI_MODEL, contents=contents, config=cfg)
            if r.text:
                return r.text
            last = AIError("Bo'sh javob")
        except Exception as e:
            last = e
        await asyncio.sleep(1.5 * (attempt + 1))
    raise AIError(str(last))


def parse_json(text):
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    return json.loads(text)


def system_prompt(user):
    return ("Sen Zehn AI — tibbiyot talabalari uchun o'quv yordamchisisan. "
            "Aniq, tushunarli va ilmiy asoslangan javob ber. Foydalanuvchi qaysi tilda yozsa, shu tilda javob ber "
            "(asosan o'zbek tilida). Tibbiy atamalarni lotincha qavs ichida keltir. "
            "Bu o'quv yordami, real bemorga tashxis yoki davo tayinlash emasligini kerak bo'lsa eslat. "
            "Bilmasang yoki ishonching komil bo'lmasa, ochiq ayt. "
            f"Talaba: {user['name']}, {user['university']}, yo'nalish: {user['direction']}.")
