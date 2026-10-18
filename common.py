import html
from aiogram.types import (ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup,
                           InlineKeyboardButton, WebAppInfo)
import db
from config import ADMIN_IDS, FREE_LIMITS

HOME = "🏠 Bosh menyu"
BACK = "⬅️ Orqaga"
CANCEL = "❌ Bekor qilish"

B_DARS, B_SLIDE, B_TEST, B_LANG = "📚 Darslik", "🖼 Slayd", "📝 Testlar", "🌍 Tillar"
B_AI, B_ABOUT, B_PREM, B_ADMIN = "🤖 AI chat", "ℹ️ Bot haqida", "💎 Premium", "🛠 Admin panel"

PREMIUM_HINT = "🔒 Bu imkoniyat Premium uchun. «💎 Premium» tugmasi orqali obuna bo'ling."

esc = html.escape


def kb(rows, placeholder=None):
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=t) for t in row] for row in rows],
        resize_keyboard=True, is_persistent=True, input_field_placeholder=placeholder)


def chunk(items, n=2):
    return [items[i:i + n] for i in range(0, len(items), n)]


def btn(text, cb=None, url=None, web=None):
    if web:
        return InlineKeyboardButton(text=text, web_app=WebAppInfo(url=web))
    if url:
        return InlineKeyboardButton(text=text, url=url)
    return InlineKeyboardButton(text=text, callback_data=cb)


def ikb(rows):
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def main_kb(uid):
    rows = [[B_DARS, B_SLIDE], [B_TEST, B_LANG], [B_AI, B_ABOUT], [B_PREM]]
    extra = [k["title"] for k in await db.children(3, True)]
    rows += chunk(extra, 2)
    if uid in ADMIN_IDS:
        rows.append([B_ADMIN])
    return kb(rows)


async def is_premium(uid):
    if uid in ADMIN_IDS:
        return True
    u = await db.get_user(uid)
    return bool(u and u["premium_until"] > db.now())


async def left(uid, feature):
    """Bugun qolgan limit. Premium bo'lsa None (cheksiz)."""
    if await is_premium(uid):
        return None
    return max(0, FREE_LIMITS[feature] - await db.used(uid, feature))


async def send_long(m, text, **kw):
    for i in range(0, len(text), 4000):
        await m.answer(text[i:i + 4000], **kw)


_username = None


async def bot_username(bot):
    global _username
    if not _username:
        _username = (await bot.me()).username
    return _username
