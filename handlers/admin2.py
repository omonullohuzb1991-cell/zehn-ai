"""Admin: slayd resurslari (shablon/rasm), so'z to'plamlari va o'yinlarni tugmaga ulash."""
import re
from aiogram import Router, F, Bot
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery
from pptx import Presentation
import ai
import db
from common import kb, btn, ikb, esc
from config import ADMIN_IDS, PUBLIC_URL
from handlers.admin import admin_kb, show, A_SLIDE, A_GAME, DONE

router = Router()
router.message.filter(F.from_user.id.in_(ADMIN_IDS))
router.callback_query.filter(F.from_user.id.in_(ADMIN_IDS))
AI_BTN = "🤖 AI bilan yaratish"
LANGS = {"🇬🇧 Ingliz tili": ("en", "Ingliz"), "🇷🇺 Rus tili": ("ru", "Rus"), "🌐 Boshqa": ("", "")}
MODES = {"all": "🎯 Hammasi (tanlov menyusi)", "flash": "🃏 Kartochkalar", "match": "🧩 Juftlikni top", "quiz": "❓ Viktorina"}


class A2(StatesGroup):
    tpl = State()
    img = State()
    ws_title = State()
    ws_lang = State()
    ws_words = State()


@router.message(F.text == DONE, StateFilter(A2.tpl, A2.img))
async def done(m: Message, state: FSMContext):
    await state.clear()
    await m.answer("✅ Tayyor.", reply_markup=admin_kb())


@router.message(StateFilter(None), F.forward_origin)
async def channel_id_helper(m: Message):
    fo = m.forward_origin
    if getattr(fo, "type", None) == "channel":
        await m.answer(f"📡 Kanal ID: <code>{fo.chat.id}</code>\nShuni <code>STORAGE_CHANNEL_ID</code> ga yozing.")


# ================= SLAYD RESURSLARI =================
async def res_list(kind):
    items = await db.assets(kind)
    if kind == "template":
        text = "📄 <b>Shablonlar</b>\nTayyor dizaynlardan tashqari foydalanuvchilar shularni ham tanlaydi.\n\n"
        text += "\n".join(f"• {esc(a['name'])}" for a in items) or "Hali yo'q."
        add = btn("➕ Shablon qo'shish", "res:at")
        dl = "res:dt"
    else:
        text = "🖼 <b>Rasmlar kutubxonasi</b>\nSlayd mavzusida kalit so'z uchrasa, rasm avtomatik qo'yiladi.\n\n"
        text += "\n".join(f"• {esc(a['name'])}: <i>{esc(a['keywords'])}</i>" for a in items[:40]) or "Hali yo'q."
        add = btn("➕ Rasm qo'shish", "res:ai")
        dl = "res:di"
    rows = [[add]] + [[btn(f"🗑 {a['name'][:30]}", f"{dl}:{a['id']}")] for a in items[:30]]
    return text, ikb(rows)


@router.message(F.text == A_SLIDE)
async def res_menu(m: Message, state: FSMContext):
    await state.clear()
    await m.answer("🎨 <b>Slayd resurslari</b>", reply_markup=ikb(
        [[btn("📄 Shablonlar", "res:tpl"), btn("🖼 Rasmlar kutubxonasi", "res:img")]]))


@router.callback_query(F.data.startswith("res:"))
async def res_cb(c: CallbackQuery, state: FSMContext):
    parts = c.data.split(":")
    act = parts[1]
    if act in ("tpl", "img"):
        text, mk = await res_list("template" if act == "tpl" else "image")
        await c.message.answer(text, reply_markup=mk)
    elif act in ("dt", "di"):
        await db.delete_asset(int(parts[2]))
        text, mk = await res_list("template" if act == "dt" else "image")
        await c.message.edit_text(text, reply_markup=mk)
    elif act == "at":
        await state.set_state(A2.tpl)
        await c.message.answer("📄 <b>.pptx</b> shablon faylini yuboring (nomi — fayl nomi yoki izoh).\n"
                               "Talab: 1-maket — titul slayd, 2-maket — «Sarlavha va matn».\nTugagach «✅ Tayyor».",
                               reply_markup=kb([[DONE]]))
    elif act == "ai":
        await state.set_state(A2.img)
        await c.message.answer("🖼 Rasm yuboring va <b>izohga kalit so'zlarni</b> vergul bilan yozing.\n"
                               "Masalan: <code>yurak, heart, cardiac</code>\nTugagach «✅ Tayyor».",
                               reply_markup=kb([[DONE]]))
    await c.answer()


@router.message(A2.tpl, F.document)
async def got_tpl(m: Message, bot: Bot):
    d = m.document
    if not (d.file_name or "").lower().endswith(".pptx"):
        return await m.answer("Faqat .pptx fayl yuboring.")
    try:
        buf = await bot.download(d)
        buf.seek(0)
        if len(Presentation(buf).slide_layouts) < 2:
            raise ValueError
    except Exception:
        return await m.answer("❌ Fayl shablon sifatida yaroqsiz (kamida 2 ta maket kerak).")
    name = (m.caption or d.file_name[:-5]).strip()[:30]
    await db.add_asset("template", name, "", d.file_id)
    await m.answer(f"✅ «{esc(name)}» shabloni qo'shildi. Yana yuboring yoki «✅ Tayyor».")


@router.message(A2.img, F.photo | F.document)
async def got_img(m: Message):
    kws = (m.caption or "").strip()
    if not kws:
        return await m.answer("❗ Izohga kalit so'zlarni yozing (masalan: yurak, heart).")
    if m.document and not (m.document.mime_type or "").startswith("image/"):
        return await m.answer("Faqat rasm yuboring.")
    fid = m.photo[-1].file_id if m.photo else m.document.file_id
    await db.add_asset("image", kws.split(",")[0].strip()[:30], kws[:200], fid)
    await m.answer("✅ Rasm qo'shildi. Yana yuboring yoki «✅ Tayyor».")


# ================= SO'Z TO'PLAMLARI / O'YINLAR =================
def parse_pairs(text):
    pairs = []
    for line in text.splitlines():
        parts = re.split(r"\s+[-–—=:]\s+|\t|\s*=\s*", line.strip(), maxsplit=1)
        if len(parts) == 2 and parts[0].strip() and parts[1].strip():
            pairs.append((parts[0].strip()[:80], parts[1].strip()[:80]))
    return pairs[:200]


@router.message(F.text == A_GAME)
async def game_menu(m: Message, state: FSMContext):
    await state.clear()
    await m.answer("🎮 <b>O'yinlar</b>\n\nAvval so'z to'plami yarating, so'ng <b>Menyu boshqaruvi → tugma → 🎮 O'yin ulash</b> "
                   "orqali o'yinni istalgan tugmaga ulang.", reply_markup=ikb([
                       [btn("➕ Yangi so'z to'plami", "gm:new")], [btn("📚 To'plamlar", "gm:list")]]))


async def sets_markup(prefix, back=None):
    ws = await db.wordsets()
    rows = [[btn(f"📚 {w['title'][:30]} ({w['n']})", f"{prefix}:{w['id']}")] for w in ws]
    return ws, ikb(rows + ([[btn("⬅️ Orqaga", back)]] if back else []))


@router.callback_query(F.data.startswith("gm:"))
async def game_cb(c: CallbackQuery, state: FSMContext):
    p = c.data.split(":")
    act = p[1]
    if act == "new":
        await state.set_state(A2.ws_title)
        await c.message.answer("To'plam nomini yozing (masalan: <i>Anatomiya atamalari</i>):")
    elif act == "list":
        ws, mk = await sets_markup("gm:v")
        await c.message.answer("📚 <b>So'z to'plamlari</b>" if ws else "Hali to'plam yo'q.", reply_markup=mk if ws else None)
    elif act == "v":
        sid = int(p[2])
        ws, words = await db.get_wordset(sid), await db.wordset_words(sid)
        if ws:
            sample = "\n".join(f"{esc(w['word'])} — {esc(w['translation'])}" for w in words[:8])
            await c.message.answer(f"📚 <b>{esc(ws['title'])}</b> ({len(words)} ta so'z)\n\n{sample}", reply_markup=ikb(
                [[btn("🗑 O'chirish", f"gm:d:{sid}")]]))
    elif act == "d":
        await db.delete_wordset(int(p[2]))
        await c.message.edit_text("🗑 To'plam o'chirildi. (Unga ulangan tugmalar bo'sh ishlaydi — ularni yangilang.)")
    elif act == "nl":                      # tugmaga o'yin ulash: to'plam tanlash
        nid = p[2]
        ws, mk = await sets_markup(f"gm:ns:{nid}")
        if not ws:
            await c.message.answer("Avval «🎮 O'yinlar» bo'limida so'z to'plami yarating.")
        else:
            await c.message.answer("Qaysi so'z to'plami bilan o'ynaladi?", reply_markup=mk)
    elif act == "ns":
        nid, sid = p[2], p[3]
        await c.message.answer("O'yin turini tanlang:", reply_markup=ikb(
            [[btn(t, f"gm:na:{nid}:{sid}:{k}")] for k, t in MODES.items()]))
    elif act == "na":
        nid, sid, mode = int(p[2]), p[3], p[4]
        if not PUBLIC_URL:
            await c.answer("PUBLIC_URL sozlanmagan (serverga chiqarilganda avtomatik bo'ladi).", show_alert=True)
            return
        await db.update_node(nid, url=f"{PUBLIC_URL}/app/?set={sid}&mode={mode}")
        await c.message.answer("✅ O'yin tugmaga ulandi!")
        await show(c.message, nid, edit=False)
    await c.answer()


@router.message(A2.ws_title, F.text)
async def ws_title(m: Message, state: FSMContext):
    await state.update_data(title=m.text.strip()[:60])
    await state.set_state(A2.ws_lang)
    await m.answer("Qaysi til?", reply_markup=kb([list(LANGS)]))


@router.message(A2.ws_lang, F.text.in_(set(LANGS)))
async def ws_lang(m: Message, state: FSMContext):
    await state.update_data(lang=m.text)
    await state.set_state(A2.ws_words)
    await m.answer("So'zlarni yuboring — har qatorda <code>so'z - tarjima</code>:\n\napple - olma\nheart - yurak\n\n"
                   "(kamida 4 ta). Yoki «🤖 AI bilan yaratish» ni bosing.", reply_markup=kb([[AI_BTN]]))


@router.message(A2.ws_words, F.text)
async def ws_words(m: Message, state: FSMContext):
    d = await state.get_data()
    code, lname = LANGS[d["lang"]]
    if m.text == AI_BTN:
        await m.answer("⏳ AI so'zlarni tayyorlamoqda...")
        prompt = (f"{lname or 'Chet'} tilini o'rganayotgan o'zbek tilli tibbiyot talabalari uchun '{d['title']}' "
                  "mavzusida 20 ta so'z yoki qisqa ibora tuz va har biriga o'zbekcha tarjima ber. "
                  'Faqat JSON: {"words":[{"w":"...","t":"..."}]}')
        try:
            data = ai.parse_json(await ai.ask(prompt, json_mode=True))
            pairs = [(str(x["w"])[:80], str(x["t"])[:80]) for x in data["words"] if x.get("w") and x.get("t")]
        except Exception:
            return await m.answer("⚠️ AI javob bera olmadi. Qayta urinib ko'ring yoki so'zlarni qo'lda yuboring.")
    else:
        pairs = parse_pairs(m.text)
    if len(pairs) < 4:
        return await m.answer("Kamida 4 ta to'g'ri qator kerak: <code>so'z - tarjima</code>")
    sid = await db.add_wordset(code, d["title"], pairs)
    await state.clear()
    await m.answer(f"✅ «{esc(d['title'])}» to'plami saqlandi ({len(pairs)} ta so'z). ID: {sid}.\n"
                   "Endi uni tugmaga ulang: Menyu boshqaruvi → tugma → 🎮 O'yin ulash.", reply_markup=admin_kb())
