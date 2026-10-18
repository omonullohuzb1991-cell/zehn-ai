import asyncio
import os
import random
import re
import tempfile
from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, FSInputFile
import ai
import db
import slides
from common import esc, kb, chunk, left, main_kb, PREMIUM_HINT, CANCEL

router = Router()
router.message.filter(F.chat.type == "private")
AI_PLAN, MANUAL = "🤖 AI reja", "✍️ Qo'lda tuzish"
SIMPLE, COMPLEX = "Oddiy (3 ta reja)", "Murakkab (5 ta reja)"


class Sl(StatesGroup):
    topic = State()
    mode = State()
    kind = State()
    manual = State()
    theme = State()


async def enter(m: Message, state: FSMContext):
    await state.clear()
    if await left(m.from_user.id, "slide") == 0:
        return await m.answer("⛔ Bugungi bepul slayd limiti tugadi (kuniga 1 ta).\n" + PREMIUM_HINT)
    await state.set_state(Sl.topic)
    await m.answer("🖼 <b>Slayd tayyorlash</b>\n\nSlayd mavzusini yozing.\nMasalan: <i>Yurak qon-tomir tizimi anatomiyasi</i>",
                   reply_markup=kb([[CANCEL]]))


@router.message(Sl.topic, F.text)
async def topic(m: Message, state: FSMContext):
    t = m.text.strip()
    if not 3 <= len(t) <= 150:
        return await m.answer("Mavzu 3–150 belgi bo'lishi kerak.")
    await state.update_data(topic=t)
    await state.set_state(Sl.mode)
    await m.answer("Reja qanday tuziladi?\n\n🤖 <b>AI reja</b> — reja avtomatik tuziladi\n"
                   "✍️ <b>Qo'lda tuzish</b> — rejani o'zingiz yozasiz", reply_markup=kb([[AI_PLAN, MANUAL], [CANCEL]]))


@router.message(Sl.mode, F.text.in_({AI_PLAN, MANUAL}))
async def mode(m: Message, state: FSMContext):
    await state.update_data(mode=m.text)
    await state.set_state(Sl.kind)
    await m.answer("Reja turini tanlang:\n\n• <b>Oddiy</b> — 3 ta reja\n"
                   "• <b>Murakkab</b> — 5 ta reja (kirish, asosiy qism, xulosa)",
                   reply_markup=kb([[SIMPLE, COMPLEX], [CANCEL]]))


@router.message(Sl.kind, F.text.in_({SIMPLE, COMPLEX}))
async def kind(m: Message, state: FSMContext):
    d = await state.get_data()
    complex_ = m.text == COMPLEX
    n = 5 if complex_ else 3
    if d["mode"] == AI_PLAN:
        await state.update_data(plan=None, n=n, complex=complex_)
        return await ask_theme(m, state)
    await state.update_data(n=n, complex=complex_)
    await state.set_state(Sl.manual)
    extra = "\n(1-qator — Kirish, 2–4 — asosiy qism, 5-qator — Xulosa)" if complex_ else ""
    await m.answer(f"✍️ Rejani yozing — <b>{n} ta band</b>, har biri yangi qatordan.{extra}\n\n"
                   "Masalan:\n1. Yurak tuzilishi\n2. Qon aylanish doiralari\n3. Yurak kasalliklari",
                   reply_markup=kb([[CANCEL]]))


@router.message(Sl.manual, F.text)
async def manual(m: Message, state: FSMContext):
    d = await state.get_data()
    lines = [re.sub(r"^\s*[\d\.\)\-•]+\s*", "", ln).strip() for ln in m.text.splitlines() if ln.strip()]
    if len(lines) != d["n"]:
        return await m.answer(f"Aynan {d['n']} ta band yozing (siz {len(lines)} ta yozdingiz).")
    await state.update_data(plan=lines)
    await ask_theme(m, state)


async def ask_theme(m: Message, state: FSMContext):
    names = list(slides.THEMES) + [f"📄 {n}" for n in (await slides.template_names())[:12]]
    await state.set_state(Sl.theme)
    await state.update_data(choices=names)
    await m.answer("🎨 Slayd dizaynini (shablonni) tanlang:", reply_markup=kb(chunk(names, 2) + [["🎲 Tasodifiy"], [CANCEL]]))


@router.message(Sl.theme, F.text)
async def choose_theme(m: Message, state: FSMContext):
    d = await state.get_data()
    if m.text != "🎲 Tasodifiy" and m.text not in d.get("choices", []):
        return await m.answer("Iltimos, pastdagi tugmalardan birini tanlang 👇")
    await generate(m, state, d["topic"], d.get("plan"), d["n"], d["complex"], m.text)


@router.message(Sl.topic)
@router.message(Sl.manual)
async def not_text(m: Message):
    await m.answer("Iltimos, matn ko'rinishida yozing ✍️")


@router.message(Sl.mode)
@router.message(Sl.kind)
@router.message(Sl.theme)
async def not_button(m: Message):
    await m.answer("Iltimos, pastdagi tugmalardan birini tanlang 👇")


def build_prompt(topic, plan, n, complex_):
    p = (f'Tibbiyot talabasi uchun "{topic}" mavzusida taqdimot matnini tayyorla. '
         "Til: o'zbek (lotin yozuvi). Tibbiy atamalarni lotincha/inglizcha qavs ichida ber. "
         f"Aynan {n} ta slayd bo'lsin (titul slaydsiz). Har slaydda 3–5 ta qisqa, mazmunli band "
         "(har biri 20 so'zdan oshmasin). ")
    if plan:
        import json
        p += "Slayd sarlavhalari aynan shular bo'lsin, shu tartibda: " + json.dumps(plan, ensure_ascii=False) + ". "
    elif complex_:
        p += "Birinchi slayd 'Kirish', oxirgisi 'Xulosa', o'rtadagi 3 tasi asosiy qism bo'lsin. "
    else:
        p += "Sarlavhalarni mavzuga mos o'zing tanla. "
    p += ('Faqat JSON qaytar: {"title": "taqdimot nomi", "slides": [{"title": "...", '
          '"bullets": ["...", "..."], "image_query": "rasm qidirish uchun 1-3 inglizcha so\'z"}]}')
    return p


async def generate(m: Message, state: FSMContext, topic, plan, n, complex_, choice=None):
    uid = m.from_user.id
    await state.clear()
    if await left(uid, "slide") == 0:
        return await m.answer("⛔ Bugungi bepul slayd limiti tugadi.\n" + PREMIUM_HINT,
                              reply_markup=await main_kb(uid))
    wait = await m.answer("⏳ Slayd tayyorlanmoqda, 1–2 daqiqa kuting...", reply_markup=await main_kb(uid))
    path = None
    try:
        raw = await ai.ask(build_prompt(topic, plan, n, complex_), json_mode=True)
        data = ai.parse_json(raw)
        if not data.get("slides"):
            raise ValueError("slides bo'sh")
        images = await slides.collect_images(data, m.bot)
        theme, tpl = None, None
        if choice and choice.startswith("📄 "):
            tpl = await slides.load_template(m.bot, choice[2:].strip())
        elif choice in slides.THEMES:
            theme = choice
        user = await db.get_user(uid)
        author = f"{user['name']}\n{user['university']}"
        fd, path = tempfile.mkstemp(suffix=".pptx")
        os.close(fd)
        await asyncio.to_thread(slides.build, data, author, path, images, theme, tpl)
        fname = (re.sub(r"[^\w\-]+", "_", topic)[:40] or "slayd") + ".pptx"
        await m.answer_document(FSInputFile(path, filename=fname), caption=f"✅ Tayyor: <b>{esc(topic)}</b>")
        await db.add_used(uid, "slide")
    except Exception:
        await m.answer("⚠️ Slaydni tayyorlashda xatolik chiqdi. Qayta urinib ko'ring "
                       "(limitingiz sarflanmadi).")
    finally:
        if path and os.path.exists(path):
            os.remove(path)
        try:
            await wait.delete()
        except Exception:
            pass
