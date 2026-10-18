"""Asosiy menyu tugmalari — har qanday holatda ishlaydi, shuning uchun birinchi ulanadi."""
from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from common import (B_DARS, B_SLIDE, B_TEST, B_LANG, B_AI, B_ABOUT, B_PREM, HOME, CANCEL,
                    is_premium, PREMIUM_HINT)
from config import FREE_CAN_USE_LANGS
from handlers import browse, ai_chat, slide, tests, account

router = Router()
router.message.filter(F.chat.type == "private")


@router.message(F.text.in_({HOME, CANCEL}))
async def home(m: Message, state: FSMContext):
    await browse.go_home(m, state)


@router.message(F.text == B_DARS)
async def darslik(m: Message, state: FSMContext):
    await state.clear()
    await browse.open_node(m, state, 1)


@router.message(F.text == B_LANG)
async def langs(m: Message, state: FSMContext):
    await state.clear()
    if not FREE_CAN_USE_LANGS and not await is_premium(m.from_user.id):
        return await m.answer("🌍 Tillar bo'limi Premium uchun ochiq.\n" + PREMIUM_HINT)
    await browse.open_node(m, state, 2)


@router.message(F.text == B_SLIDE)
async def sl(m: Message, state: FSMContext):
    await slide.enter(m, state)


@router.message(F.text == B_TEST)
async def ts(m: Message, state: FSMContext):
    await tests.enter(m, state)


@router.message(F.text == B_AI)
async def ac(m: Message, state: FSMContext):
    await ai_chat.enter(m, state)


@router.message(F.text == B_PREM)
async def prem(m: Message, state: FSMContext):
    await account.enter(m, state)


@router.message(F.text == B_ABOUT)
async def about(m: Message, state: FSMContext):
    await state.clear()
    await browse.show_about(m)
