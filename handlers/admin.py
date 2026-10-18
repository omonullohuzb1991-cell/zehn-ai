import asyncio
import re
from datetime import datetime
from aiogram import Router, F, Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, BufferedInputFile
import db
from common import kb, chunk, btn, ikb, esc, main_kb, HOME, B_ADMIN
from config import ADMIN_IDS, STORAGE_CHANNEL_ID

router = Router()
router.message.filter(F.from_user.id.in_(ADMIN_IDS))
router.callback_query.filter(F.from_user.id.in_(ADMIN_IDS))

PROT = {1, 2, 3, 4}  # asosiy bo'limlar — o'chirib/nomini o'zgartirib bo'lmaydi
A_MENU, A_STAT, A_USER, A_BC, A_PAY, A_BACKUP = ("🗂 Menyu boshqaruvi", "📊 Statistika", "👥 Foydalanuvchi",
                                                  "📢 Xabar yuborish", "💳 To'lovlar", "💾 Zaxira nusxa")
A_SLIDE, A_GAME = "🎨 Slayd resurslari", "🎮 O'yinlar"
DONE = "✅ Tayyor"


class A(StatesGroup):
    add = State()
    name = State()
    text = State()
    url = State()
    mat = State()
    uid = State()
    bal = State()
    bc = State()
    reason = State()


def admin_kb():
    return kb([[A_MENU, A_STAT], [A_USER, A_BC], [A_PAY, A_BACKUP], [A_SLIDE, A_GAME], [HOME]])


async def enter(m: Message, state: FSMContext):
    await state.clear()
    await m.answer("🛠 <b>Admin panel</b>", reply_markup=admin_kb())


@router.message(F.text == B_ADMIN)
async def open_panel(m: Message, state: FSMContext):
    await enter(m, state)


# ================= MENYU DARAXTI =================
async def render(nid):
    if nid == 0:
        rows = [[btn(k["title"], f"adm:e:{k['id']}")] for k in await db.children(0)]
        rows.append([btn("✖️ Yopish", "adm:close:0")])
        return "🗂 <b>Asosiy bo'limlar</b>\nTahrirlash uchun bo'limni tanlang:", ikb(rows)
    n = await db.node(nid)
    kids = await db.children(nid)
    mats = await db.materials(nid)
    text = f"📍 <b>{esc(await db.path(nid))}</b>\n"
    text += f"📝 Matn: {esc((n['text'] or '—')[:150])}\n🔗 WebApp: {esc(n['url'] or '—')}\n"
    text += f"📎 Materiallar: {len(mats)} • 📁 Ichki tugmalar: {len(kids)}\n"
    if n["hidden"]:
        text += "🙈 <i>Foydalanuvchilardan yashirilgan</i>\n"
    rows = chunk([btn(("🙈 " if k["hidden"] else "📁 ") + k["title"], f"adm:e:{k['id']}") for k in kids], 2)
    rows.append([btn("➕ Tugma qo'shish", f"adm:a:{nid}")])
    first = [btn("📝 Matn", f"adm:t:{nid}")]
    if nid not in PROT:
        first.insert(0, btn("✏️ Nomi", f"adm:n:{nid}"))
    rows.append(first)
    rows.append([btn(f"📎 Material qo'shish", f"adm:m:{nid}"), btn("🔗 WebApp havola", f"adm:u:{nid}")])
    rows.append([btn("🎮 O'yin ulash", f"gm:nl:{nid}")])
    if mats:
        rows.append([btn("🧹 Materiallarni tozalash", f"adm:c:{nid}")])
    if nid not in PROT:
        rows.append([btn("🙈/👁 Yashirish", f"adm:h:{nid}"), btn("⬆️", f"adm:ku:{nid}"), btn("⬇️", f"adm:kd:{nid}")])
        rows.append([btn("🗑 O'chirish", f"adm:x:{nid}")])
    rows.append([btn("⬅️ Yuqoriga", f"adm:e:{n['parent_id']}")])
    return text, ikb(rows)


async def show(target, nid, edit=True):
    text, mk = await render(nid)
    if edit:
        try:
            await target.edit_text(text, reply_markup=mk)
        except TelegramBadRequest:
            pass
    else:
        await target.answer(text, reply_markup=mk)


@router.message(F.text == A_MENU)
async def menu_mgr(m: Message, state: FSMContext):
    await state.clear()
    await show(m, 0, edit=False)


@router.callback_query(F.data.startswith("adm:"))
async def tree_cb(c: CallbackQuery, state: FSMContext):
    _, act, sid = c.data.split(":")
    nid = int(sid)
    msg = c.message
    if act == "close":
        await msg.delete()
    elif act == "e":
        await show(msg, nid)
    elif act == "a":
        await state.set_state(A.add)
        await state.update_data(nid=nid)
        await msg.answer("Yangi tugma nomini yozing (emoji bilan chiroyli chiqadi, masalan: 🫀 Yurak):")
    elif act == "n":
        await state.set_state(A.name)
        await state.update_data(nid=nid)
        await msg.answer("Yangi nomni yozing:")
    elif act == "t":
        await state.set_state(A.text)
        await state.update_data(nid=nid)
        await msg.answer("Bu tugma bosilganda chiqadigan matnni yozing (HTML: &lt;b&gt;, &lt;i&gt; mumkin).\n"
                         "Matnni o'chirish uchun «-» yuboring.")
    elif act == "u":
        await state.set_state(A.url)
        await state.update_data(nid=nid)
        await msg.answer("Mini App (o'yin/so'z yodlash) havolasini yuboring — <code>https://</code> bilan boshlansin.\n"
                         "O'chirish uchun «-» yuboring.")
    elif act == "m":
        await state.set_state(A.mat)
        await state.update_data(nid=nid)
        await msg.answer("📎 Materiallarni yuboring: slayd, video, audio, PDF, rasm, matn — istalgancha. "
                         "Forward qilingan xabarlar ham bo'ladi (kanaldan).\nTugagach «✅ Tayyor» ni bosing.",
                         reply_markup=kb([[DONE]]))
    elif act == "c":
        await db.clear_materials(nid)
        await show(msg, nid)
    elif act == "h":
        n = await db.node(nid)
        await db.update_node(nid, hidden=0 if n["hidden"] else 1)
        await show(msg, nid)
    elif act in ("ku", "kd"):
        await db.move(nid, -1 if act == "ku" else 1)
        n = await db.node(nid)
        await show(msg, n["parent_id"])
    elif act == "x":
        await msg.edit_text("❗ Bu tugma va uning ichidagi hamma narsa o'chadi. Tasdiqlaysizmi?", reply_markup=ikb(
            [[btn("✅ Ha, o'chir", f"adm:xy:{nid}"), btn("❌ Yo'q", f"adm:e:{nid}")]]))
    elif act == "xy":
        n = await db.node(nid)
        if n and nid not in PROT:
            await db.delete_node(nid)
            await show(msg, n["parent_id"])
    await c.answer()


@router.message(A.add, F.text)
async def add_node(m: Message, state: FSMContext):
    nid = (await state.get_data())["nid"]
    new = await db.add_node(nid, m.text.strip()[:60])
    await state.clear()
    await m.answer("✅ Tugma qo'shildi. Endi unga matn/material qo'shishingiz mumkin:", reply_markup=admin_kb())
    await show(m, new, edit=False)


@router.message(A.name, F.text)
async def set_name(m: Message, state: FSMContext):
    nid = (await state.get_data())["nid"]
    await db.update_node(nid, title=m.text.strip()[:60])
    await state.clear()
    await show(m, nid, edit=False)


@router.message(A.text, F.text)
async def set_text(m: Message, state: FSMContext):
    nid = (await state.get_data())["nid"]
    val = None if m.text.strip() == "-" else m.html_text
    await db.update_node(nid, text=val)
    await state.clear()
    await show(m, nid, edit=False)


@router.message(A.url, F.text)
async def set_url(m: Message, state: FSMContext):
    t = m.text.strip()
    if t != "-" and not t.startswith("https://"):
        return await m.answer("Havola <code>https://</code> bilan boshlanishi shart (Telegram talabi).")
    nid = (await state.get_data())["nid"]
    await db.update_node(nid, url=None if t == "-" else t)
    await state.clear()
    await show(m, nid, edit=False)


LINK = re.compile(r"https?://t\.me/c/(\d+)/(?:\d+/)?(\d+)")


@router.message(A.mat)
async def add_mat(m: Message, state: FSMContext, bot: Bot):
    nid = (await state.get_data())["nid"]
    if m.text == DONE:
        await state.clear()
        await m.answer("✅ Materiallar saqlandi.", reply_markup=admin_kb())
        return await show(m, nid, edit=False)
    chat_id, msg_id = m.chat.id, m.message_id
    link = LINK.search(m.text or "")
    fo = m.forward_origin
    if link:    # kanal xabari havolasi (t.me/c/...)
        chat_id, msg_id = int("-100" + link.group(1)), int(link.group(2))
        try:
            await bot.copy_message(m.chat.id, chat_id, msg_id)   # tekshiruv + ko'rinish
        except Exception:
            return await m.answer("❌ Bu xabarni ola olmadim. Bot kanalga admin sifatida qo'shilganmi?")
    elif STORAGE_CHANNEL_ID:
        if fo and getattr(fo, "type", None) == "channel" and fo.chat.id == STORAGE_CHANNEL_ID:
            chat_id, msg_id = fo.chat.id, fo.message_id          # kanaldan forward qilingan
        else:                                                    # kanalga ko'chirib saqlaymiz
            try:
                c = await bot.copy_message(STORAGE_CHANNEL_ID, m.chat.id, m.message_id)
                chat_id, msg_id = STORAGE_CHANNEL_ID, c.message_id
            except Exception:
                await m.answer("⚠️ Kanalga saqlab bo'lmadi (bot kanal admini ekanini tekshiring). "
                               "Hozircha shaxsiy chatingizga bog'lab saqladim.")
    await db.add_material(nid, chat_id, msg_id)
    await m.answer("➕ Qo'shildi. Yana yuboring yoki «✅ Tayyor» ni bosing.")


# ================= STATISTIKA / ZAXIRA =================
@router.message(F.text == A_STAT)
async def stat(m: Message):
    s = await db.global_stats()
    await m.answer(f"📊 <b>Statistika</b>\n\n👥 Jami: {s['total']}\n✅ Ro'yxatdan o'tgan: {s['reg']}\n"
                   f"💎 Faol Premium: {s['prem']}\n🔥 Bugun faol: {s['active']}\n📝 Testlar: {s['tests']}\n"
                   f"💰 Tasdiqlangan to'lovlar: {s['income']:,} so'm".replace(",", " "))


@router.message(F.text == A_BACKUP)
async def backup(m: Message):
    data = await db.export_json()
    await m.answer_document(BufferedInputFile(data, filename=f"zehn_backup_{datetime.now():%Y%m%d_%H%M}.json"),
                            caption="💾 Zaxira. Tiklash uchun shu faylni «restore» izohi bilan botga yuboring.")


@router.message(F.document, F.caption == "restore")
async def restore(m: Message, bot: Bot):
    buf = await bot.download(m.document)
    try:
        await db.import_json(buf.read())
    except Exception:
        return await m.answer("❌ Fayl yaroqsiz yoki zaxira formati noto'g'ri. Baza o'zgarmadi.")
    await m.answer("✅ Baza tiklandi.")


# ================= TO'LOVLAR =================
@router.message(F.text == A_PAY)
async def pay_list(m: Message):
    rows = await db.pending_payments()
    if not rows:
        return await m.answer("Kutilayotgan to'lovlar yo'q ✅")
    for p in rows:
        u = await db.get_user(p["user_id"])
        cap = f"💳 <b>To'lov #{p['id']}</b>\n👤 {esc(u['name'] or '')} (<code>{p['user_id']}</code>)\n💰 {p['amount']:,} so'm".replace(",", " ")
        await m.answer_photo(p["check_file"], caption=cap, reply_markup=ikb(
            [[btn("✅ Tasdiqlash", f"pay:ok:{p['id']}"), btn("❌ Rad etish", f"pay:no:{p['id']}")]]))


@router.callback_query(F.data.startswith("pay:"))
async def pay_cb(c: CallbackQuery, state: FSMContext, bot: Bot):
    _, act, sid = c.data.split(":")
    pid = int(sid)
    p = await db.get_payment(pid)
    if not p or p["status"] != "pending":
        return await c.answer("Bu to'lov allaqachon ko'rib chiqilgan", show_alert=True)
    if act == "ok":
        if await db.resolve_payment(pid, "ok"):
            await db.add_balance(p["user_id"], p["amount"])
            try:
                await bot.send_message(p["user_id"], f"✅ To'lovingiz tasdiqlandi! Hisobingizga "
                                       f"<b>{p['amount']:,} so'm</b> qo'shildi.".replace(",", " "))
            except Exception:
                pass
            await c.message.edit_caption(caption=(c.message.caption or "") + "\n\n✅ <b>Tasdiqlandi</b>")
    else:
        await state.set_state(A.reason)
        await state.update_data(pid=pid)
        await c.message.answer(f"#{pid} to'lov rad etilmoqda. Foydalanuvchiga yuboriladigan <b>sababni</b> yozing:")
    await c.answer()


@router.message(A.reason, F.text)
async def pay_reason(m: Message, state: FSMContext, bot: Bot):
    pid = (await state.get_data())["pid"]
    p = await db.get_payment(pid)
    await state.clear()
    if p and await db.resolve_payment(pid, "no"):
        try:
            await bot.send_message(p["user_id"], f"❌ To'lovingiz rad etildi.\nSabab: {esc(m.text)}\n"
                                   "Muammo bo'lsa, qaytadan urinib ko'ring.")
        except Exception:
            pass
        await m.answer("Rad etildi, foydalanuvchiga xabar yuborildi.", reply_markup=admin_kb())
    else:
        await m.answer("To'lov allaqachon ko'rib chiqilgan.", reply_markup=admin_kb())


# ================= FOYDALANUVCHI =================
@router.message(F.text == A_USER)
async def user_ask(m: Message, state: FSMContext):
    await state.set_state(A.uid)
    await m.answer("Foydalanuvchi Telegram ID raqamini yozing:")


@router.message(A.uid, F.text)
async def user_show(m: Message, state: FSMContext):
    if not m.text.strip().isdigit():
        return await m.answer("ID faqat raqamlardan iborat.")
    uid = int(m.text.strip())
    u = await db.get_user(uid)
    await state.clear()
    if not u:
        return await m.answer("Bunday foydalanuvchi topilmadi.", reply_markup=admin_kb())
    until = datetime.fromtimestamp(u["premium_until"], db.TZ).strftime("%d.%m.%Y") if u["premium_until"] > db.now() else "yo'q"
    await m.answer(f"👤 {esc(u['name'] or '—')} (@{u['username'] or '—'})\n🏛 {esc(u['university'] or '—')} • {esc(u['direction'] or '—')}\n"
                   f"💰 Balans: {u['balance']} so'm\n💎 Premium: {until}", reply_markup=ikb([
                       [btn("+30 kun", f"usr:p30:{uid}"), btn("+90 kun", f"usr:p90:{uid}"), btn("+180 kun", f"usr:p180:{uid}")],
                       [btn("💰 Balans qo'shish", f"usr:bal:{uid}"), btn("🚫 Premiumni olish", f"usr:p0:{uid}")]]))


@router.callback_query(F.data.startswith("usr:"))
async def user_cb(c: CallbackQuery, state: FSMContext, bot: Bot):
    _, act, sid = c.data.split(":")
    uid = int(sid)
    if act == "bal":
        await state.set_state(A.bal)
        await state.update_data(uid=uid)
        await c.message.answer("Qo'shiladigan summani yozing (so'm):")
    elif act == "p0":
        await db.set_user(uid, premium_until=0)
        await c.message.answer("Premium olib tashlandi.")
    else:
        await db.give_premium(uid, int(act[1:]))
        await c.message.answer(f"✅ {act[1:]} kun Premium berildi.")
        try:
            await bot.send_message(uid, f"🎁 Sizga {act[1:]} kunlik 💎 Premium berildi!")
        except Exception:
            pass
    await c.answer()


@router.message(A.bal, F.text)
async def bal_add(m: Message, state: FSMContext):
    t = m.text.replace(" ", "")
    if not t.lstrip("-").isdigit():
        return await m.answer("Faqat raqam yozing.")
    uid = (await state.get_data())["uid"]
    await db.add_balance(uid, int(t))
    await state.clear()
    await m.answer("✅ Balans yangilandi.", reply_markup=admin_kb())


# ================= XABAR YUBORISH =================
@router.message(F.text == A_BC)
async def bc_ask(m: Message, state: FSMContext):
    await state.set_state(A.bc)
    await m.answer("📢 Hamma foydalanuvchilarga yuboriladigan xabarni yuboring (matn, rasm, video — istalgani).")


@router.message(A.bc)
async def bc_preview(m: Message, state: FSMContext):
    await state.clear()
    await m.answer("Yuqoridagi xabar yuborilsinmi?", reply_to_message_id=m.message_id, reply_markup=ikb(
        [[btn("✅ Yuborish", f"bc:yes:{m.message_id}"), btn("❌ Bekor", "bc:no:0")]]))


@router.callback_query(F.data.startswith("bc:"))
async def bc_go(c: CallbackQuery, bot: Bot):
    _, act, sid = c.data.split(":")
    if act == "no":
        await c.message.edit_text("Bekor qilindi.")
        return await c.answer()
    await c.message.edit_text("⏳ Yuborilmoqda...")
    ok = fail = 0
    for uid in await db.registered_ids():
        try:
            await bot.copy_message(uid, c.message.chat.id, int(sid))
            ok += 1
        except Exception:
            fail += 1
        await asyncio.sleep(0.05)
    await c.message.answer(f"✅ Yuborildi: {ok}\n❌ Yetib bormadi: {fail}")
    await c.answer()
