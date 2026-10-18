import asyncio
import logging
import os
import time
import aiohttp
from aiogram import Bot, Dispatcher, BaseMiddleware
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BufferedInputFile, ErrorEvent
from aiohttp import web
import db
from common import esc
from config import BOT_TOKEN, ADMIN_IDS, PORT, PUBLIC_URL, WEBAPP_DIR
from handlers import start, menu, admin, admin2, browse, ai_chat, slide, account, tests, fallback


class RegMiddleware(BaseMiddleware):
    """Shaxsiy chatda: foydalanuvchini bazaga yozadi va ro'yxatdan o'tmaganlarni /start ga yo'naltiradi."""

    async def __call__(self, handler, event, data):
        if event.chat.type != "private" or not event.from_user:
            return await handler(event, data)
        await db.upsert_user(event.from_user)
        u = await db.get_user(event.from_user.id)
        if u["banned"]:
            return
        if not u["registered"]:
            st = await data["state"].get_state()
            if not st and not (event.text or "").startswith("/start"):
                await event.answer("Botdan foydalanish uchun avval ro'yxatdan o'ting 👉 /start")
                return
        return await handler(event, data)


async def health_server():
    async def ok(_):
        return web.Response(text="Zehn AI ishlayapti ✅")
    async def app_page(_):
        return web.FileResponse(os.path.join(WEBAPP_DIR, "index.html"), headers={"Cache-Control": "no-cache"})

    async def api_set(req):
        try:
            sid = int(req.match_info["id"])
        except ValueError:
            return web.json_response({"error": "bad id"}, status=400)
        ws = await db.get_wordset(sid)
        if not ws:
            return web.json_response({"error": "not found"}, status=404)
        words = await db.wordset_words(sid)
        return web.json_response({"title": ws["title"], "lang": ws["lang"],
                                  "words": [{"w": w["word"], "t": w["translation"]} for w in words]})

    app = web.Application()
    app.router.add_get("/", ok)
    app.router.add_get("/health", ok)
    app.router.add_get("/app", app_page)
    app.router.add_get("/app/", app_page)
    app.router.add_get("/api/set/{id}", api_set)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", PORT).start()


async def keepalive_loop():
    """Render bepul xizmati uxlab qolmasligi uchun o'z manzilini har 10 daqiqada chaqiradi."""
    if not PUBLIC_URL:
        return
    while True:
        await asyncio.sleep(600)
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as s:
                await s.get(PUBLIC_URL + "/health")
        except Exception:
            pass


async def backup_loop(bot: Bot):
    """Har 12 soatda baza nusxasini adminga yuboradi (qo'shimcha himoya)."""
    while True:
        await asyncio.sleep(12 * 3600)
        try:
            data = await db.export_json()
        except Exception:
            continue
        for aid in ADMIN_IDS:
            try:
                await bot.send_document(aid, BufferedInputFile(data, filename="zehn_backup.json"),
                                        caption="💾 Avtomatik zaxira")
            except Exception:
                pass


async def main():
    logging.basicConfig(level=logging.INFO)
    if not BOT_TOKEN:
        raise SystemExit("BOT_TOKEN topilmadi. .env faylini to'ldiring.")
    await db.init()
    bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())
    dp.message.outer_middleware(RegMiddleware())
    # TARTIB MUHIM: menyu tugmalari va admin birinchi, umumiy (fallback) oxirgi
    dp.include_routers(menu.router, admin.router, admin2.router, start.router, account.router, slide.router,
                       tests.router, tests.group_router, ai_chat.router, browse.router, fallback.router)

    last_alert = {"t": 0.0}

    @dp.errors()
    async def on_error(event: ErrorEvent):
        logging.exception("Kutilmagan xato", exc_info=event.exception)
        if time.time() - last_alert["t"] < 60:   # adminni spam qilmaslik
            return True
        last_alert["t"] = time.time()
        for aid in ADMIN_IDS:
            try:
                await bot.send_message(aid, f"⚠️ <b>Botda xato:</b>\n<code>{esc(repr(event.exception)[:600])}</code>")
            except Exception:
                pass
        return True

    await health_server()
    asyncio.create_task(backup_loop(bot))
    asyncio.create_task(keepalive_loop())
    await bot.delete_webhook(drop_pending_updates=True)
    logging.info("Bot ishga tushdi")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
