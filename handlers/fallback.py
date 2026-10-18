from aiogram import Router, F
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
import db
from common import main_kb
from handlers import browse

router = Router()
router.message.filter(F.chat.type == "private")


@router.message(StateFilter(None), F.text)
async def custom_or_unknown(m: Message, state: FSMContext):
    # Admin «Bosh menyu qo'shimcha tugmalari» (3-bo'lim) orqali qo'shgan tugmalar
    for k in await db.children(3, True):
        if k["title"] == m.text:
            return await browse.open_node(m, state, k["id"])
    await m.answer("Iltimos, pastdagi tugmalardan foydalaning 👇", reply_markup=await main_kb(m.from_user.id))
