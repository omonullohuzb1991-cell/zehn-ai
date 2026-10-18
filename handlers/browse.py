from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message
import db
from common import kb, chunk, esc, btn, ikb, main_kb, is_premium, HOME, BACK, bot_username
from config import FREE_LIMITS

router = Router()
router.message.filter(F.chat.type == "private")


class Browse(StatesGroup):
    node = State()


async def send_materials(bot, uid, nid):
    for mt in await db.materials(nid):
        try:
            await bot.copy_message(chat_id=uid, from_chat_id=mt["chat_id"], message_id=mt["message_id"])
        except Exception:
            pass  # material o'chirilgan bo'lishi mumkin


async def open_node(m: Message, state: FSMContext, nid: int):
    uid = m.chat.id
    n = await db.node(nid)
    if not n:
        return await m.answer("Bo'lim topilmadi.", reply_markup=await main_kb(uid))
    kids = await db.children(nid, True)
    mats = await db.materials(nid)
    await state.set_state(Browse.node)
    await state.update_data(node=nid)
    text = f"<b>{esc(n['title'])}</b>"
    if n["text"]:
        text += "\n\n" + n["text"]
    if kids:
        text += "\n\n👇 Bo'limni tanlang:"
    elif not mats and not n["url"] and not n["text"]:
        text += "\n\nBu bo'lim hozircha bo'sh. Tez orada to'ldiriladi 🛠"
    await m.answer(text, reply_markup=kb(chunk([k["title"] for k in kids], 2) + [[BACK, HOME]]))

    if mats:
        allowed = True
        if await db.root_of(nid) == 1 and not await is_premium(uid):
            feat = f"darslik:{nid}"
            if await db.used(uid, feat) == 0:
                if await db.distinct_used(uid, "darslik:") >= FREE_LIMITS["darslik"]:
                    allowed = False
                else:
                    await db.add_used(uid, feat)
        if allowed:
            await send_materials(m.bot, uid, nid)
        else:
            await m.answer("🔒 Bepul rejada kuniga faqat bitta mavzu materiallari ochiladi.\n"
                           "Cheksiz foydalanish uchun «💎 Premium» bo'limiga o'ting.")
    if n["url"]:
        await m.answer("🔗 Ochish uchun bosing:", reply_markup=ikb([[btn("🚀 Ochish", web=n["url"])]]))


async def go_home(m: Message, state: FSMContext):
    await state.clear()
    await m.answer("🏠 Bosh menyu", reply_markup=await main_kb(m.chat.id))


async def show_about(m: Message):
    n = await db.node(4)
    if n["text"]:
        await m.answer(n["text"])
    await send_materials(m.bot, m.chat.id, 4)
    me = await bot_username(m.bot)
    link = f"https://t.me/{me}"
    await m.answer("Do'stlaringizga ulashing yoki guruhingizga qo'shing 👇", reply_markup=ikb([
        [btn("📤 Ulashish", url=f"https://t.me/share/url?url={link}&text=Zehn%20AI%20—%20talabalar%20uchun%20yordamchi%20bot")],
        [btn("➕ Guruhga qo'shish", url=f"{link}?startgroup=true")]]))


@router.message(Browse.node, F.text == BACK)
async def back(m: Message, state: FSMContext):
    cur = (await state.get_data()).get("node")
    n = await db.node(cur) if cur else None
    if not n or n["parent_id"] == 0:
        return await go_home(m, state)
    await open_node(m, state, n["parent_id"])


@router.message(Browse.node, F.text)
async def choose(m: Message, state: FSMContext):
    cur = (await state.get_data()).get("node")
    for k in await db.children(cur, True):
        if k["title"] == m.text:
            return await open_node(m, state, k["id"])
    await m.answer("Iltimos, pastdagi tugmalardan birini tanlang 👇")
