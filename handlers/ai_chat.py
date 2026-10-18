from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message
import ai
import db
from common import kb, left, send_long, main_kb, PREMIUM_HINT

router = Router()
router.message.filter(F.chat.type == "private")
EXIT = "⬅️ Chatdan chiqish"


class Chat(StatesGroup):
    active = State()


async def enter(m: Message, state: FSMContext):
    await state.clear()
    await state.set_state(Chat.active)
    await state.update_data(hist=[])
    l = await left(m.from_user.id, "ai")
    info = "cheksiz (Premium)" if l is None else f"bugun qolgan savollar: {l}"
    await m.answer(f"🤖 <b>AI chat</b> yoqildi — {info}.\nSavolingizni yozing ✍️",
                   reply_markup=kb([[EXIT]], "Savolingizni yozing..."))


@router.message(Chat.active, F.text == EXIT)
async def leave(m: Message, state: FSMContext):
    await state.clear()
    await m.answer("Chatdan chiqdingiz.", reply_markup=await main_kb(m.from_user.id))


@router.message(Chat.active, F.text)
async def talk(m: Message, state: FSMContext):
    uid = m.from_user.id
    if await left(uid, "ai") == 0:
        return await m.answer("⛔ Bugungi bepul savollar tugadi.\n" + PREMIUM_HINT)
    await m.bot.send_chat_action(m.chat.id, "typing")
    d = await state.get_data()
    hist = d.get("hist", [])
    user = await db.get_user(uid)
    try:
        answer = await ai.ask(m.text, system=ai.system_prompt(user), history=hist)
    except ai.AIError:
        return await m.answer("⚠️ AI hozir javob bera olmadi. Birozdan so'ng qayta urinib ko'ring "
                              "(limitingiz sarflanmadi).")
    await db.add_used(uid, "ai")
    hist += [("user", m.text), ("model", answer)]
    await state.update_data(hist=hist[-10:])
    await send_long(m, answer, parse_mode=None)


@router.message(Chat.active)
async def non_text(m: Message):
    await m.answer("Iltimos, savolni matn ko'rinishida yozing ✍️")
