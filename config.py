import os
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_IDS = {int(x) for x in os.getenv("ADMIN_IDS", "").replace(" ", "").split(",") if x.isdigit()}
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
UNSPLASH_KEY = os.getenv("UNSPLASH_KEY", "")
CARD_NUMBER = os.getenv("CARD_NUMBER", "0000 0000 0000 0000")
CARD_OWNER = os.getenv("CARD_OWNER", "")
DATABASE_URL = os.getenv("DATABASE_URL", "")  # Neon/Supabase Postgres ulanish manzili
PORT = int(os.getenv("PORT", "8080"))
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")
IMAGE_DIR = os.path.join(BASE_DIR, "images")

# ---- Bepul foydalanuvchi limitlari (kuniga) ----
FREE_LIMITS = {"ai": 5, "slide": 1, "darslik": 1}
FREE_CAN_TAKE_TESTS = False   # True qilsangiz bepul foydalanuvchilar ham test ishlay oladi
FREE_CAN_USE_LANGS = False    # True qilsangiz Tillar bo'limi hamma uchun ochiq

# ---- Premium tariflar: nomi -> (kun, narx so'm) ----
PLANS = {
    "1 oylik": (30, 30000),
    "3 oylik": (90, 80000),
    "6 oylik": (180, 165000),
}
MIN_TOPUP = 5000
GROUP_SECONDS = 30  # guruhdagi testda har savolga beriladigan vaqt

# ---- Kanal va Mini App ----
STORAGE_CHANNEL_ID = int(os.getenv("STORAGE_CHANNEL_ID", "0") or 0)  # materiallar saqlanadigan yopiq kanal
PUBLIC_URL = (os.getenv("PUBLIC_URL") or os.getenv("RENDER_EXTERNAL_URL") or "").rstrip("/")
WEBAPP_DIR = os.path.join(BASE_DIR, "webapp")
