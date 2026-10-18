from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message
from datetime import datetime
import db
from common import kb, btn, ikb, esc, main_kb, is_premium, left, HOME, CANCEL
from config import PLANS, CARD_NUMBER, CARD_OWNER, MIN_TOPUP, ADMIN_IDS, FREE_LIMITS

router = Router()
router.message.filter(F.chat.type == "private")
B_BUY, B_TOP, B_ME = "💎 Premium sotib olish", "💳 Hisobni to'ldirish", "👤 Hisobim"


def fmt(n):
    return f"{n:,}".replace(",", " ")


PLAN_BTN = {f"{name} — {fmt(price)} so'm": name for name, (days, price) in PLANS.items()}


class Pay(StatesGroup):
    amount = State()
    check = State()


def prem_kb():
    return kb([[B_BUY, B_TOP], [B_ME], [HOME]])


async def enter(m: Message, state: FSMContext):
    await state.clear()
    await m.answer("💎 <b>Premium</b> — barcha bo'limlar cheksiz va ochiq.\n\n"
                   + "\n".join(f"• {n}: <b>{fmt(p)} so'm</b>" for n, (d, p) in PLANS.items()),
                   reply_markup=prem_kb())


@router.message(F.text == B_ME)
async def me(m: Message, state: FSMContext):
    await state.clear()
    uid = m.from_user.id
    u = await db.get_user(uid)
    if await is_premium(uid):
        until = "cheksiz (admin)" if uid in ADMIN_IDS and u["premium_until"] < db.now() else \
            datetime.fromtimestamp(u["premium_until"], db.TZ).strftime("%d.%m.%Y")
        status = f"💎 Premium ({until} gacha)"
        lim = "Barcha imkoniyatlar cheksiz ✅"
    else:
        status = "🆓 Bepul"
        dl = max(0, FREE_LIMITS["darslik"] - await db.distinct_used(uid, "darslik:"))
        lim = (f"Bugun qolgan limitlar:\n• AI chat: {await left(uid, 'ai')}\n"
               f"• Slayd: {await left(uid, 'slide')}\n• Darslik mavzusi: {dl}")
    await m.answer(f"👤 <b>{esc(u['name'] or '')}</b>\n🏛 {esc(u['university'] or '')} • {esc(u['direction'] or '')}\n\n"
                   f"💰 Balans: <b>{fmt(u['balance'])} so'm</b>\n📌 Holat: {status}\n\n{lim}", reply_markup=prem_kb())


@router.message(F.text == B_BUY)
async def buy_menu(m: Message, state: FSMContext):
    await state.clear()
    u = await db.get_user(m.from_user.id)
    await m.answer(f"💰 Balansingiz: <b>{fmt(u['balance'])} so'm</b>\nTarifni tanlang 👇",
                   reply_markup=kb([[t] for t in PLAN_BTN] + [[B_TOP], [HOME]]))


@router.message(F.text.in_(set(PLAN_BTN)))
async def buy(m: Message):
    days, price = PLANS[PLAN_BTN[m.text]]
    u = await db.get_user(m.from_user.id)
    if u["balance"] < price:
        return await m.answer(f"❗ Balansingizda mablag' yetarli emas.\nKerak: {fmt(price)} so'm, "
                              f"mavjud: {fmt(u['balance'])} so'm.\n«{B_TOP}» tugmasi orqali hisobni to'ldiring.")
    if await db.buy_premium(m.from_user.id, days, price):
        u = await db.get_user(m.from_user.id)
        until = datetime.fromtimestamp(u["premium_until"], db.TZ).strftime("%d.%m.%Y")
        await m.answer(f"🎉 Premium faollashtirildi! <b>{until}</b> gacha barcha imkoniyatlar ochiq.",
                       reply_markup=prem_kb())
    else:
        await m.answer("Xatolik: mablag' yetarli emas.")


@router.message(F.text == B_TOP)
async def topup(m: Message, state: FSMContext):
    await state.clear()
    await state.set_state(Pay.amount)
    await m.answer(f"💳 <b>Hisobni to'ldirish</b>\n\nKarta: <code>{esc(CARD_NUMBER)}</code>\n"
                   f"Egasi: {esc(CARD_OWNER)}\n\nUzCard/Humo ilovangiz orqali pulni shu kartaga o'tkazing, "
                   f"so'ng <b>necha so'm tashlaganingizni</b> raqamda yozing (kamida {fmt(MIN_TOPUP)}).",
                   reply_markup=kb([[CANCEL]]))


@router.message(Pay.amount, F.text)
async def amount(m: Message, state: FSMContext):
    t = m.text.replace(" ", "").replace(",", "")
    if not t.isdigit() or not MIN_TOPUP <= int(t) <= 50_000_000:
        return await m.answer(f"Summani faqat raqamda yozing (kamida {fmt(MIN_TOPUP)} so'm). Masalan: 30000")
    await state.update_data(amount=int(t))
    await state.set_state(Pay.check)
    await m.answer("🧾 Endi to'lov <b>chekining rasmini (skrinshot)</b> yuboring.")


@router.message(Pay.check, F.photo)
async def check(m: Message, state: FSMContext):
    d = await state.get_data()
    fid = m.photo[-1].file_id
    pid = await db.add_payment(m.from_user.id, d["amount"], fid)
    await state.clear()
    u = await db.get_user(m.from_user.id)
    cap = (f"💳 <b>Yangi to'lov #{pid}</b>\n👤 {esc(u['name'] or '')} (<code>{m.from_user.id}</code>)\n"
           f"💰 Summa: <b>{fmt(d['amount'])} so'm</b>")
    mk = ikb([[btn("✅ Tasdiqlash", f"pay:ok:{pid}"), btn("❌ Rad etish", f"pay:no:{pid}")]])
    for aid in ADMIN_IDS:
        try:
            await m.bot.send_photo(aid, fid, caption=cap, reply_markup=mk)
        except Exception:
            pass
    await m.answer("✅ Chek qabul qilindi. Admin tekshirgach hisobingiz to'ldiriladi va sizga xabar beramiz.",
                   reply_markup=prem_kb())


@router.message(Pay.check)
async def check_bad(m: Message):
    await m.answer("Iltimos, chek <b>rasmini</b> yuboring 🧾")


@router.message(Pay.amount)
async def amount_bad(m: Message):
    await m.answer("Summani raqamda yozing. Masalan: 30000")
