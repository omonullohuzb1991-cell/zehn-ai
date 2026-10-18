"""Quiz-bot uslubidagi test tizimi (Telegram quiz so'rovnomalari asosida)."""
import asyncio
import json
import random
from aiogram import Router, F, Bot
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, PollAnswer
import ai
import db
from common import kb, btn, ikb, esc, main_kb, is_premium, bot_username, PREMIUM_HINT, CANCEL, HOME
from config import ADMIN_IDS, FREE_CAN_TAKE_TESTS, GROUP_SECONDS

router = Router()
router.message.filter(F.chat.type == "private")
group_router = Router()
group_router.message.filter(F.chat.type.in_({"group", "supergroup"}))

NEW, AITEST, MINE, FINISH = "➕ Yangi test", "🤖 AI bilan test", "📂 Mening testlarim", "✅ Tugatish"
SESS = {}          # poll_id -> (run, to'g'ri javob indeksi)
GROUP_ACTIVE = set()


class TS(StatesGroup):
    title = State()
    polls = State()
    rename = State()
    ai_topic = State()
    ai_count = State()


def tests_kb():
    return kb([[NEW, AITEST], [MINE], [HOME]])


async def can_take(uid):
    return FREE_CAN_TAKE_TESTS or await is_premium(uid)


async def enter(m: Message, state: FSMContext):
    await state.clear()
    await m.answer("📝 <b>Testlar</b>\n\nImtihonga tayyorlanish yoki o'zaro sinov o'tkazish uchun testlar.",
                   reply_markup=tests_kb())


# ---------------- karta ----------------
async def card(tid, uid):
    t = await db.get_test(tid)
    if not t:
        return None
    n = len(await db.questions(tid))
    rows = [[btn("▶️ Boshlash", f"t:run:{tid}"), btn("🔗 Ulashish", f"t:share:{tid}")]]
    if t["owner_id"] == uid or uid in ADMIN_IDS:
        rows += [[btn("👥 Guruhda o'tkazish", f"t:group:{tid}"), btn("📊 Statistika", f"t:stat:{tid}")],
                 [btn("✏️ Tahrirlash", f"t:edit:{tid}"), btn("🗑 O'chirish", f"t:del:{tid}")]]
    return f"📝 <b>{esc(t['title'])}</b>\nSavollar soni: <b>{n}</b>", ikb(rows)


async def send_card(m: Message, tid):
    r = await card(tid, m.chat.id)
    if not r:
        return await m.answer("Test topilmadi yoki o'chirilgan.")
    await m.answer(r[0], reply_markup=r[1])


async def owns(c: CallbackQuery, tid):
    t = await db.get_test(tid)
    if t and (t["owner_id"] == c.from_user.id or c.from_user.id in ADMIN_IDS):
        return True
    await c.answer("Bu test sizniki emas", show_alert=True)
    return False


# ---------------- yaratish ----------------
@router.message(F.text == NEW)
async def new_test(m: Message, state: FSMContext):
    if not await can_take(m.from_user.id):
        return await m.answer(PREMIUM_HINT)
    await state.clear()
    await state.set_state(TS.title)
    await m.answer("Test nomini yozing:", reply_markup=kb([[CANCEL]]))


@router.message(TS.title, F.text)
async def got_title(m: Message, state: FSMContext):
    t = m.text.strip()
    if not 2 <= len(t) <= 100:
        return await m.answer("Nom 2–100 belgi bo'lsin.")
    await state.update_data(title=t, qs=[], test_id=None)
    await state.set_state(TS.polls)
    await m.answer(POLL_HELP, reply_markup=kb([[FINISH], [CANCEL]]))


POLL_HELP = ("Endi savollarni yuboring:\n📎 → <b>So'rovnoma (Poll)</b> → <b>Viktorina rejimi (Quiz mode)</b> yoqing, "
             "savol, variantlar va to'g'ri javobni belgilab yuboring. Har bir savol alohida so'rovnoma bo'ladi.\n"
             "Hammasini yuborib bo'lgach «✅ Tugatish» ni bosing.")


@router.message(TS.polls, F.poll)
async def got_poll(m: Message, state: FSMContext):
    p = m.poll
    if p.type != "quiz" or p.correct_option_id is None:
        return await m.answer("❗ Faqat <b>Viktorina (Quiz)</b> rejimidagi so'rovnoma yuboring va to'g'ri javobni belgilang.")
    d = await state.get_data()
    qs = d.get("qs", [])
    qs.append({"question": p.question[:300], "options": [o.text[:100] for o in p.options],
               "correct": p.correct_option_id, "explanation": (p.explanation or "")[:200]})
    await state.update_data(qs=qs)
    await m.answer(f"✅ {len(qs)}-savol qo'shildi. Yana yuboring yoki «{FINISH}» ni bosing.")


@router.message(TS.polls, F.text == FINISH)
async def finish_poll(m: Message, state: FSMContext):
    d = await state.get_data()
    qs = d.get("qs", [])
    if not qs:
        return await m.answer("Hali birorta savol qo'shilmadi.")
    tid = d.get("test_id") or await db.add_test(m.from_user.id, d["title"])
    await db.add_questions(tid, qs)
    await state.clear()
    await m.answer(f"🎉 {len(qs)} ta savol saqlandi!", reply_markup=tests_kb())
    await send_card(m, tid)


@router.message(TS.polls)
async def polls_other(m: Message):
    await m.answer("Quiz so'rovnomasini yuboring yoki «✅ Tugatish» ni bosing.")


# ---------------- AI test ----------------
@router.message(F.text == AITEST)
async def ai_test(m: Message, state: FSMContext):
    if not await can_take(m.from_user.id):
        return await m.answer(PREMIUM_HINT)
    await state.clear()
    await state.set_state(TS.ai_topic)
    await m.answer("Test mavzusini yozing (masalan: <i>Yurak anatomiyasi</i>):", reply_markup=kb([[CANCEL]]))


@router.message(TS.ai_topic, F.text)
async def ai_topic(m: Message, state: FSMContext):
    await state.update_data(topic=m.text.strip()[:150])
    await state.set_state(TS.ai_count)
    await m.answer("Nechta savol bo'lsin?", reply_markup=kb([["5", "10", "15"], [CANCEL]]))


@router.message(TS.ai_count, F.text.in_({"5", "10", "15"}))
async def ai_count(m: Message, state: FSMContext):
    d = await state.get_data()
    n = int(m.text)
    await state.clear()
    wait = await m.answer("⏳ Savollar tayyorlanmoqda...", reply_markup=tests_kb())
    prompt = (f'"{d["topic"]}" mavzusida tibbiyot talabalari uchun {n} ta test savoli tuz. Har birida 4 ta variant, '
              "bitta to'g'ri javob. Til: o'zbek (lotin). Faqat JSON: "
              '{"questions":[{"question":"...","options":["...","...","...","..."],"correct":0,"explanation":"qisqa izoh"}]}')
    try:
        data = ai.parse_json(await ai.ask(prompt, json_mode=True))
        qs = []
        for q in data["questions"]:
            opts, c = list(q["options"]), int(q["correct"])
            if not 2 <= len(opts) <= 10 or not 0 <= c < len(opts):
                continue
            order = list(range(len(opts)))
            random.shuffle(order)
            qs.append({"question": str(q["question"])[:300], "options": [str(opts[i])[:100] for i in order],
                       "correct": order.index(c), "explanation": str(q.get("explanation", ""))[:200]})
        if not qs:
            raise ValueError
    except Exception:
        await wait.delete()
        return await m.answer("⚠️ Savollarni yaratib bo'lmadi. Qayta urinib ko'ring.")
    tid = await db.add_test(m.from_user.id, d["topic"])
    await db.add_questions(tid, qs)
    await wait.delete()
    await send_card(m, tid)


# ---------------- ro'yxat va tahrir ----------------
@router.message(F.text == MINE)
async def mine(m: Message, state: FSMContext):
    await state.clear()
    ts = await db.user_tests(m.from_user.id)
    if not ts:
        return await m.answer("Sizda hali test yo'q. «➕ Yangi test» orqali yarating.")
    await m.answer("📂 <b>Sizning testlaringiz:</b>",
                   reply_markup=ikb([[btn(f"📝 {t['title'][:40]}", f"t:open:{t['id']}")] for t in ts]))


@router.message(TS.rename, F.text)
async def do_rename(m: Message, state: FSMContext):
    tid = (await state.get_data())["test_id"]
    await db.rename_test(tid, m.text.strip()[:100])
    await state.clear()
    await m.answer("✅ Nom o'zgartirildi.", reply_markup=tests_kb())
    await send_card(m, tid)


async def q_list(c: CallbackQuery, tid):
    qs = await db.questions(tid)
    if not qs:
        return await c.message.edit_text("Savollar yo'q.", reply_markup=ikb([[btn("⬅️ Orqaga", f"t:edit:{tid}")]]))
    text = "\n".join(f"{i}. {esc(q['question'][:60])}" for i, q in enumerate(qs, 1))
    rows = [[btn(f"🗑 {i}", f"t:dq:{q['id']}") for i, q in enumerate(qs, 1)][j:j + 5] for j in range(0, len(qs), 5)]
    rows.append([btn("⬅️ Orqaga", f"t:edit:{tid}")])
    await c.message.edit_text("<b>Savollar</b> (o'chirish uchun raqamni bosing):\n\n" + text, reply_markup=ikb(rows))


@router.callback_query(F.data.startswith("t:"))
async def cb(c: CallbackQuery, state: FSMContext, bot: Bot):
    _, act, sid = c.data.split(":")
    xid = int(sid)
    uid = c.from_user.id
    if act == "dq":
        q = await db.get_question(xid)
        if q and await owns(c, q["test_id"]):
            await db.delete_question(xid)
            await c.answer("O'chirildi")
            await q_list(c, q["test_id"])
        return
    tid = xid
    if act == "open":
        r = await card(tid, uid)
        if r:
            await c.message.edit_text(r[0], reply_markup=r[1])
    elif act == "run":
        if not await can_take(uid):
            return await c.answer("Test ishlash Premium uchun 💎", show_alert=True)
        await start_private(bot, uid, c.from_user.full_name, tid)
    elif act == "share":
        me = await bot_username(bot)
        await c.message.answer(f"🔗 Testni ulashish havolasi:\nhttps://t.me/{me}?start=t_{tid}")
    elif act == "group":
        me = await bot_username(bot)
        await c.message.answer(
            "👥 <b>Guruhda o'tkazish:</b>\n1) Botni guruhga qo'shing va admin qiling.\n"
            f"2) Guruhda yozing: <code>/test {tid}</code>",
            reply_markup=ikb([[btn("➕ Guruhga qo'shish", url=f"https://t.me/{me}?startgroup=true")]]))
    elif act == "stat":
        if not await owns(c, tid):
            return
        agg, top = await db.test_stats(tid)
        txt = f"📊 <b>Statistika</b>\nUrinishlar: {agg['n']}\nO'rtacha natija: {round(agg['avg'] or 0)}%\n"
        if top:
            txt += "\n🏆 Eng yaxshilar:\n" + "\n".join(
                f"{i}. {esc(r['name'])} — {r['c']}/{r['total']}" for i, r in enumerate(top, 1))
        await c.message.answer(txt)
    elif act == "edit":
        if not await owns(c, tid):
            return
        await c.message.edit_text("✏️ <b>Tahrirlash</b>", reply_markup=ikb([
            [btn("📝 Nomini o'zgartirish", f"t:ren:{tid}")], [btn("➕ Savol qo'shish", f"t:addq:{tid}")],
            [btn("🗂 Savollarni ko'rish/o'chirish", f"t:qs:{tid}")], [btn("⬅️ Orqaga", f"t:open:{tid}")]]))
    elif act == "ren":
        if await owns(c, tid):
            await state.clear()
            await state.set_state(TS.rename)
            await state.update_data(test_id=tid)
            await c.message.answer("Yangi nomni yozing:", reply_markup=kb([[CANCEL]]))
    elif act == "addq":
        if await owns(c, tid):
            await state.clear()
            await state.set_state(TS.polls)
            await state.update_data(test_id=tid, qs=[], title="")
            await c.message.answer(POLL_HELP, reply_markup=kb([[FINISH], [CANCEL]]))
    elif act == "qs":
        if await owns(c, tid):
            await q_list(c, tid)
    elif act == "del":
        if await owns(c, tid):
            await c.message.edit_text("❗ Testni o'chirishni tasdiqlaysizmi?", reply_markup=ikb(
                [[btn("✅ Ha", f"t:delok:{tid}"), btn("❌ Yo'q", f"t:open:{tid}")]]))
    elif act == "delok":
        if await owns(c, tid):
            await db.delete_test(tid)
            await c.message.edit_text("🗑 Test o'chirildi.")
    await c.answer()


# ---------------- testni o'tkazish ----------------
async def send_q(bot: Bot, run):
    q = run["qs"][run["i"]]
    opts = json.loads(q["options"])
    msg = await bot.send_poll(
        chat_id=run["chat"], question=f"{run['i'] + 1}/{len(run['qs'])}. {q['question']}"[:300],
        options=opts, type="quiz", correct_option_id=q["correct"], is_anonymous=False,
        explanation=(q["explanation"] or "")[:200] or None, open_period=run.get("secs"))
    SESS[msg.poll.id] = (run, q["correct"])
    run["polls"].append(msg.poll.id)


def cleanup(run):
    for pid in run["polls"]:
        SESS.pop(pid, None)


def new_run(tid, qs, chat, mode, secs=None):
    return {"tid": tid, "qs": qs, "i": 0, "chat": chat, "mode": mode, "secs": secs,
            "scores": {}, "done": set(), "polls": []}


async def start_private(bot: Bot, uid, name, tid):
    qs = await db.questions(tid)
    if not qs:
        return await bot.send_message(uid, "Bu testda savollar yo'q.")
    run = new_run(tid, qs, uid, "private")
    run["scores"][uid] = {"name": name, "c": 0, "n": 0}
    await bot.send_message(uid, f"▶️ Test boshlandi: {len(qs)} ta savol. Omad! 🍀")
    await send_q(bot, run)


@router.poll_answer()
@group_router.poll_answer()
async def on_answer(pa: PollAnswer, bot: Bot):
    item = SESS.get(pa.poll_id)
    if not item or not pa.option_ids:
        return
    run, correct = item
    uid = pa.user.id
    key = (pa.poll_id, uid)
    if key in run["done"]:
        return
    run["done"].add(key)
    s = run["scores"].setdefault(uid, {"name": pa.user.full_name, "c": 0, "n": 0})
    s["n"] += 1
    s["c"] += int(pa.option_ids[0] == correct)
    if run["mode"] != "private":
        return
    run["i"] += 1
    await asyncio.sleep(1.2)
    if run["i"] < len(run["qs"]):
        await send_q(bot, run)
    else:
        total = len(run["qs"])
        await db.add_result(run["tid"], uid, s["name"], s["c"], total)
        pct = round(s["c"] * 100 / total)
        medal = "🏆" if pct >= 85 else "👍" if pct >= 60 else "📚"
        cleanup(run)
        await bot.send_message(run["chat"], f"{medal} <b>Test yakunlandi!</b>\nNatija: <b>{s['c']}/{total}</b> ({pct}%)",
                               reply_markup=ikb([[btn("🔁 Qayta ishlash", f"t:run:{run['tid']}")]]))


@group_router.message(Command("test"))
async def group_test(m: Message, command: CommandObject, bot: Bot):
    if not command.args or not command.args.strip().isdigit():
        return await m.reply("Foydalanish: /test <test raqami>")
    tid = int(command.args.strip())
    t = await db.get_test(tid)
    if not t:
        return await m.reply("Test topilmadi.")
    uid = m.from_user.id
    allowed = uid == t["owner_id"] or uid in ADMIN_IDS
    if not allowed:
        mem = await bot.get_chat_member(m.chat.id, uid)
        allowed = mem.status in ("administrator", "creator")
    if not allowed:
        return await m.reply("Testni faqat test egasi yoki guruh adminlari boshlay oladi.")
    if m.chat.id in GROUP_ACTIVE:
        return await m.reply("Bu guruhda test allaqachon ketmoqda.")
    qs = await db.questions(tid)
    if not qs:
        return await m.reply("Bu testda savollar yo'q.")
    asyncio.create_task(group_run(bot, m.chat.id, tid, t["title"], qs))


async def group_run(bot: Bot, chat_id, tid, title, qs):
    GROUP_ACTIVE.add(chat_id)
    run = new_run(tid, qs, chat_id, "group", GROUP_SECONDS)
    try:
        await bot.send_message(chat_id, f"📝 <b>{esc(title)}</b>\n{len(qs)} ta savol, har biriga {GROUP_SECONDS} soniya.\n"
                                        "Tayyor bo'ling! 3 soniyadan so'ng boshlanadi...")
        await asyncio.sleep(3)
        for i in range(len(qs)):
            run["i"] = i
            await send_q(bot, run)
            await asyncio.sleep(GROUP_SECONDS + 1.5)
        board = sorted(run["scores"].items(), key=lambda kv: -kv[1]["c"])[:10]
        lines = [f"{['🥇', '🥈', '🥉'][i] if i < 3 else str(i + 1) + '.'} {esc(s['name'])} — {s['c']}/{len(qs)}"
                 for i, (_, s) in enumerate(board)]
        for uid, s in run["scores"].items():
            await db.add_result(tid, uid, s["name"], s["c"], len(qs))
        await bot.send_message(chat_id, "🏁 <b>Test yakunlandi!</b>\n\n" + ("\n".join(lines) or "Hech kim qatnashmadi."))
    finally:
        cleanup(run)
        GROUP_ACTIVE.discard(chat_id)
