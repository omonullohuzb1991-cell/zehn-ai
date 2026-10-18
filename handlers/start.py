from aiogram import Router, F
from aiogram.filters import CommandStart, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, ReplyKeyboardRemove
import db
from common import kb, main_kb, esc, CANCEL
from handlers import tests

router = Router()
router.message.filter(F.chat.type == "private")
DIRECTIONS = ["Davolash ishi", "Pediatriya"]


class Reg(StatesGroup):
    name = State()
    uni = State()
    direction = State()


async def welcome(m: Message, payload=None):
    u = await db.get_user(m.from_user.id)
    await m.answer(f"Assalomu alaykum, <b>{esc(u['name'] or m.from_user.first_name)}</b>! 👋\n"
                   "<b>Zehn AI</b> botiga xush kelibsiz. Kerakli bo'limni tanlang 👇",
                   reply_markup=await main_kb(m.from_user.id))
    if payload and payload.startswith("t_") and payload[2:].isdigit():
        await tests.send_card(m, int(payload[2:]))


@router.message(CommandStart())
async def start(m: Message, state: FSMContext, command: CommandObject):
    await state.clear()
    u = await db.get_user(m.from_user.id)
    if u["registered"]:
        return await welcome(m, command.args)
    await state.update_data(payload=command.args)
    await state.set_state(Reg.name)
    await m.answer("👋 Salom! <b>Zehn AI</b> — talabalar uchun yordamchi bot.\n"
                   "Sizga moslashishimiz uchun qisqa ro'yxatdan o'tamiz.\n\n"
                   "1/3 — <b>Ism va familiyangizni</b> yozing:", reply_markup=ReplyKeyboardRemove())


@router.message(Reg.name, F.text)
async def reg_name(m: Message, state: FSMContext):
    t = m.text.strip()
    if not 3 <= len(t) <= 80:
        return await m.answer("Iltimos, ism va familiyangizni to'liq yozing (3–80 belgi).")
    await state.update_data(name=t)
    await state.set_state(Reg.uni)
    await m.answer("2/3 — <b>Oliy ta'lim muassasasi</b> nomini yozing:")


@router.message(Reg.uni, F.text)
async def reg_uni(m: Message, state: FSMContext):
    t = m.text.strip()
    if not 2 <= len(t) <= 120:
        return await m.answer("Iltimos, muassasa nomini to'g'ri yozing.")
    await state.update_data(uni=t)
    await state.set_state(Reg.direction)
    await m.answer("3/3 — <b>Ta'lim yo'nalishingizni</b> tanlang 👇", reply_markup=kb([DIRECTIONS]))


@router.message(Reg.direction, F.text)
async def reg_dir(m: Message, state: FSMContext):
    if m.text not in DIRECTIONS:
        return await m.answer("Iltimos, pastdagi tugmalardan birini tanlang 👇")
    d = await state.get_data()
    await db.set_user(m.from_user.id, name=d["name"], university=d["uni"], direction=m.text, registered=1)
    await state.clear()
    await m.answer("✅ Ro'yxatdan o'tdingiz!")
    await welcome(m, d.get("payload"))


@router.message(Reg.name)
@router.message(Reg.uni)
async def reg_nontext(m: Message):
    await m.answer("Iltimos, matn ko'rinishida yozing ✍️")
