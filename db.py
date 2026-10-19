import asyncio
import json
import re
import time
from datetime import datetime, timezone, timedelta
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

import asyncpg
from config import BOT_NAME, DATABASE_URL

TZ = timezone(timedelta(hours=5))  # O'zbekiston vaqti
TABLES = ["users", "nodes", "materials", "usage_log", "payments", "tests", "questions", "results",
          "assets", "wordsets", "words"]
SERIAL = ["nodes", "materials", "payments", "tests", "questions", "results", "assets", "wordsets", "words"]


def today():
    return datetime.now(TZ).strftime("%Y-%m-%d")


def now():
    return int(time.time())


_pool = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(
  id BIGINT PRIMARY KEY, username TEXT, name TEXT, university TEXT, direction TEXT,
  registered INTEGER DEFAULT 0, balance BIGINT DEFAULT 0, premium_until BIGINT DEFAULT 0,
  banned INTEGER DEFAULT 0, created BIGINT);
CREATE TABLE IF NOT EXISTS nodes(
  id BIGSERIAL PRIMARY KEY, parent_id BIGINT NOT NULL, title TEXT NOT NULL,
  text TEXT, url TEXT, pos INTEGER DEFAULT 0, hidden INTEGER DEFAULT 0);
CREATE INDEX IF NOT EXISTS idx_nodes_parent ON nodes(parent_id);
CREATE TABLE IF NOT EXISTS materials(
  id BIGSERIAL PRIMARY KEY, node_id BIGINT, chat_id BIGINT, message_id BIGINT);
CREATE INDEX IF NOT EXISTS idx_materials_node ON materials(node_id);
CREATE TABLE IF NOT EXISTS usage_log(
  user_id BIGINT, day TEXT, feature TEXT, cnt INTEGER DEFAULT 0, PRIMARY KEY(user_id, day, feature));
CREATE TABLE IF NOT EXISTS payments(
  id BIGSERIAL PRIMARY KEY, user_id BIGINT, amount BIGINT, check_file TEXT,
  status TEXT DEFAULT 'pending', created BIGINT);
CREATE TABLE IF NOT EXISTS tests(
  id BIGSERIAL PRIMARY KEY, owner_id BIGINT, title TEXT, created BIGINT);
CREATE TABLE IF NOT EXISTS questions(
  id BIGSERIAL PRIMARY KEY, test_id BIGINT, question TEXT, options TEXT,
  correct INTEGER, explanation TEXT);
CREATE INDEX IF NOT EXISTS idx_questions_test ON questions(test_id);
CREATE TABLE IF NOT EXISTS results(
  id BIGSERIAL PRIMARY KEY, test_id BIGINT, user_id BIGINT, name TEXT,
  correct INTEGER, total INTEGER, created BIGINT);
CREATE TABLE IF NOT EXISTS assets(
  id BIGSERIAL PRIMARY KEY, kind TEXT, name TEXT, keywords TEXT, file_id TEXT, created BIGINT);
CREATE TABLE IF NOT EXISTS wordsets(
  id BIGSERIAL PRIMARY KEY, lang TEXT, title TEXT, created BIGINT);
CREATE TABLE IF NOT EXISTS words(
  id BIGSERIAL PRIMARY KEY, set_id BIGINT, word TEXT, translation TEXT);
CREATE INDEX IF NOT EXISTS idx_words_set ON words(set_id);
"""


def _dsn():
    """Neon bergan manzildagi asyncpg tushunmaydigan parametrlarni olib tashlaydi."""
    p = urlsplit(DATABASE_URL)
    q = [(k, v) for k, v in parse_qsl(p.query) if k != "channel_binding"]
    return urlunsplit((p.scheme, p.netloc, p.path, urlencode(q), ""))


async def init(seed=True):
    global _pool
    if not DATABASE_URL:
        raise SystemExit("DATABASE_URL topilmadi. .env fayliga Neon manzilini yozing.")
    _pool = await asyncpg.create_pool(
        _dsn(), min_size=1, max_size=5, timeout=30, command_timeout=30,
        statement_cache_size=0,                 # Neon pooler (pgbouncer) bilan ishlashi uchun
        max_inactive_connection_lifetime=60)    # Neon uxlaganda eskirgan ulanishlar qolmasin
    async with _pool.acquire() as c:
        await c.execute(SCHEMA)
    if seed:
        await seed_defaults()


async def close():
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


def _q(sql):
    i = 0

    def r(_):
        nonlocal i
        i += 1
        return f"${i}"
    return re.sub(r"\?", r, sql)


async def _retry(fn):
    for attempt in range(3):
        try:
            return await fn()
        except (asyncpg.PostgresConnectionError, asyncpg.InterfaceError, ConnectionResetError, OSError):
            if attempt == 2:
                raise
            await asyncio.sleep(1 + attempt)


async def fetch(sql, args=()):
    async def f():
        async with _pool.acquire() as c:
            return await c.fetch(_q(sql), *args)
    return await _retry(f)


async def one(sql, args=()):
    async def f():
        async with _pool.acquire() as c:
            return await c.fetchrow(_q(sql), *args)
    return await _retry(f)


async def run(sql, args=()):
    """Yozish so'rovi. O'zgargan qatorlar sonini qaytaradi."""
    async def f():
        async with _pool.acquire() as c:
            status = await c.execute(_q(sql), *args)
            tail = status.split()[-1]
            return int(tail) if tail.isdigit() else 0
    return await _retry(f)


async def insert(sql, args=()):
    """INSERT qiladi va yangi qator id sini qaytaradi."""
    async def f():
        async with _pool.acquire() as c:
            return await c.fetchval(_q(sql) + " RETURNING id", *args)
    return await _retry(f)


async def seed_defaults():
    if await one("SELECT 1 FROM nodes LIMIT 1"):
        return
    roots = ["📚 Darslik", "🌍 Tillar", "Bosh menyu qo'shimcha tugmalari", "ℹ️ Bot haqida"]
    about = (f"<b>{BOT_NAME}</b> — talabalar uchun yordamchi bot.\n\n"
             "📚 Darslik • 🖼 Slayd tayyorlash • 📝 Testlar • 🌍 Tillar • 🤖 AI chat")
    async with _pool.acquire() as c, c.transaction():
        for i, t in enumerate(roots, 1):
            await c.execute("INSERT INTO nodes(id,parent_id,title,pos) VALUES($1,0,$2,$3)", i, t, i)
        await c.execute("UPDATE nodes SET text=$1 WHERE id=4", about)
        await c.execute("SELECT setval(pg_get_serial_sequence('nodes','id'), (SELECT MAX(id) FROM nodes))")
        for p, t in enumerate(["🫀 Anatomiya", "🔬 Gistologiya"]):
            await c.execute("INSERT INTO nodes(parent_id,title,pos) VALUES(1,$1,$2)", t, p)
        for p, lang in enumerate(["🇬🇧 Ingliz tili", "🇷🇺 Rus tili"]):
            lid = await c.fetchval("INSERT INTO nodes(parent_id,title,pos) VALUES(2,$1,$2) RETURNING id", lang, p)
            for q, sub in enumerate(["📖 Books", "🧠 So'z yodlash", "🎮 Game"]):
                await c.execute("INSERT INTO nodes(parent_id,title,pos) VALUES($1,$2,$3)", lid, sub, q)


# ---------------- zaxira (JSON) ----------------
async def export_json():
    data = {}
    for t in TABLES:
        data[t] = [dict(r) for r in await fetch(f"SELECT * FROM {t}")]
    return json.dumps(data, ensure_ascii=False, default=str).encode("utf-8")


async def import_json(raw):
    """Zaxira faylidan butun bazani qayta tiklaydi (mavjud ma'lumotlar o'chadi)."""
    data = json.loads(raw)
    if not isinstance(data, dict) or not set(data) <= set(TABLES):
        raise ValueError("noto'g'ri zaxira fayli")
    ident = re.compile(r"^[a-z_]+$")
    async with _pool.acquire() as c, c.transaction():
        await c.execute("TRUNCATE " + ",".join(TABLES) + " RESTART IDENTITY")
        for t, rows in data.items():
            for row in rows:
                cols = list(row)
                if not all(ident.match(k) for k in cols):
                    raise ValueError("noto'g'ri ustun")
                ph = ",".join(f"${i + 1}" for i in range(len(cols)))
                await c.execute(f"INSERT INTO {t}({','.join(cols)}) VALUES({ph})", *[row[k] for k in cols])
        for t in SERIAL:
            await c.execute(f"SELECT setval(pg_get_serial_sequence('{t}','id'), "
                            f"COALESCE((SELECT MAX(id) FROM {t}),0)+1, false)")


# ---------------- users ----------------
async def upsert_user(u):
    await run("INSERT INTO users(id,created) VALUES(?,?) ON CONFLICT (id) DO NOTHING", (u.id, now()))
    await run("UPDATE users SET username=? WHERE id=?", (u.username, u.id))


async def get_user(uid):
    return await one("SELECT * FROM users WHERE id=?", (uid,))


async def set_user(uid, **f):
    allowed = {"name", "university", "direction", "registered", "banned", "premium_until"}
    f = {k: v for k, v in f.items() if k in allowed}
    if not f:
        return
    await run("UPDATE users SET " + ",".join(f"{k}=?" for k in f) + " WHERE id=?", (*f.values(), uid))


async def add_balance(uid, amount):
    await run("UPDATE users SET balance=balance+? WHERE id=?", (amount, uid))


async def buy_premium(uid, days, price):
    """Balansdan yechib, premiumni uzaytiradi. Muvaffaqiyatli bo'lsa True (bitta atomik so'rov)."""
    n = await run("""UPDATE users SET balance=balance-?,
                       premium_until=GREATEST(?, premium_until)+?
                     WHERE id=? AND balance>=?""", (price, now(), days * 86400, uid, price))
    return n > 0


async def give_premium(uid, days):
    await run("UPDATE users SET premium_until=GREATEST(?, premium_until)+? WHERE id=?",
              (now(), days * 86400, uid))


async def registered_ids():
    return [r["id"] for r in await fetch("SELECT id FROM users WHERE registered=1 AND banned=0")]


async def global_stats():
    r = await one("""SELECT COUNT(*) AS total, COALESCE(SUM(registered),0)::bigint AS reg,
        COALESCE(SUM(CASE WHEN premium_until>? THEN 1 ELSE 0 END),0)::bigint AS prem FROM users""", (now(),))
    t = await one("SELECT COUNT(*) AS n FROM tests")
    p = await one("SELECT COALESCE(SUM(amount),0)::bigint AS s FROM payments WHERE status='ok'")
    a = await one("SELECT COUNT(DISTINCT user_id) AS n FROM usage_log WHERE day=?", (today(),))
    return dict(total=r["total"], reg=r["reg"], prem=r["prem"], tests=t["n"], income=p["s"], active=a["n"])


# ---------------- nodes ----------------
async def node(nid):
    return await one("SELECT * FROM nodes WHERE id=?", (nid,))


async def children(pid, visible=False):
    sql = "SELECT * FROM nodes WHERE parent_id=?" + (" AND hidden=0" if visible else "") + " ORDER BY pos,id"
    return await fetch(sql, (pid,))


async def root_of(nid):
    while True:
        n = await node(nid)
        if not n or n["parent_id"] == 0:
            return nid
        nid = n["parent_id"]


async def path(nid):
    parts = []
    while nid:
        n = await node(nid)
        if not n:
            break
        parts.append(n["title"])
        nid = n["parent_id"]
    return " › ".join(reversed(parts))


async def add_node(pid, title):
    r = await one("SELECT COALESCE(MAX(pos),0)+1 AS p FROM nodes WHERE parent_id=?", (pid,))
    return await insert("INSERT INTO nodes(parent_id,title,pos) VALUES(?,?,?)", (pid, title, r["p"]))


async def update_node(nid, **f):
    f = {k: v for k, v in f.items() if k in {"title", "text", "url", "hidden"}}
    if f:
        await run("UPDATE nodes SET " + ",".join(f"{k}=?" for k in f) + " WHERE id=?", (*f.values(), nid))


async def delete_node(nid):
    ids, stack = [], [nid]
    while stack:
        cur = stack.pop()
        ids.append(cur)
        stack += [c["id"] for c in await children(cur)]
    async with _pool.acquire() as c, c.transaction():
        await c.execute("DELETE FROM materials WHERE node_id = ANY($1::bigint[])", ids)
        await c.execute("DELETE FROM nodes WHERE id = ANY($1::bigint[])", ids)


async def move(nid, d):
    n = await node(nid)
    ids = [s["id"] for s in await children(n["parent_id"])]
    i = ids.index(nid)
    j = i + d
    if 0 <= j < len(ids):
        ids[i], ids[j] = ids[j], ids[i]
    async with _pool.acquire() as c, c.transaction():
        await c.executemany("UPDATE nodes SET pos=$1 WHERE id=$2", [(p, x) for p, x in enumerate(ids)])


async def materials(nid):
    return await fetch("SELECT * FROM materials WHERE node_id=? ORDER BY id", (nid,))


async def add_material(nid, chat_id, message_id):
    await run("INSERT INTO materials(node_id,chat_id,message_id) VALUES(?,?,?)", (nid, chat_id, message_id))


async def clear_materials(nid):
    await run("DELETE FROM materials WHERE node_id=?", (nid,))


# ---------------- usage / limits ----------------
async def used(uid, feature):
    r = await one("SELECT cnt FROM usage_log WHERE user_id=? AND day=? AND feature=?", (uid, today(), feature))
    return r["cnt"] if r else 0


async def add_used(uid, feature):
    await run("""INSERT INTO usage_log(user_id,day,feature,cnt) VALUES(?,?,?,1)
                 ON CONFLICT(user_id,day,feature) DO UPDATE SET cnt=usage_log.cnt+1""", (uid, today(), feature))


async def distinct_used(uid, prefix):
    r = await one("SELECT COUNT(*) AS c FROM usage_log WHERE user_id=? AND day=? AND feature LIKE ?",
                  (uid, today(), prefix + "%"))
    return r["c"]


# ---------------- payments ----------------
async def add_payment(uid, amount, file_id):
    return await insert("INSERT INTO payments(user_id,amount,check_file,created) VALUES(?,?,?,?)",
                        (uid, amount, file_id, now()))


async def get_payment(pid):
    return await one("SELECT * FROM payments WHERE id=?", (pid,))


async def resolve_payment(pid, status):
    return await run("UPDATE payments SET status=? WHERE id=? AND status='pending'", (status, pid)) > 0


async def pending_payments():
    return await fetch("SELECT * FROM payments WHERE status='pending' ORDER BY id LIMIT 10")


# ---------------- tests ----------------
async def add_test(owner, title):
    return await insert("INSERT INTO tests(owner_id,title,created) VALUES(?,?,?)", (owner, title, now()))


async def get_test(tid):
    return await one("SELECT * FROM tests WHERE id=?", (tid,))


async def user_tests(uid):
    return await fetch("SELECT * FROM tests WHERE owner_id=? ORDER BY id DESC LIMIT 30", (uid,))


async def rename_test(tid, title):
    await run("UPDATE tests SET title=? WHERE id=?", (title, tid))


async def delete_test(tid):
    async with _pool.acquire() as c, c.transaction():
        await c.execute("DELETE FROM questions WHERE test_id=$1", tid)
        await c.execute("DELETE FROM results WHERE test_id=$1", tid)
        await c.execute("DELETE FROM tests WHERE id=$1", tid)


async def questions(tid):
    return await fetch("SELECT * FROM questions WHERE test_id=? ORDER BY id", (tid,))


async def add_questions(tid, qs):
    rows = [(tid, q["question"], json.dumps(q["options"], ensure_ascii=False), q["correct"],
             q.get("explanation") or "") for q in qs]
    async with _pool.acquire() as c, c.transaction():
        await c.executemany("INSERT INTO questions(test_id,question,options,correct,explanation) "
                            "VALUES($1,$2,$3,$4,$5)", rows)


async def get_question(qid):
    return await one("SELECT * FROM questions WHERE id=?", (qid,))


async def delete_question(qid):
    await run("DELETE FROM questions WHERE id=?", (qid,))


async def add_result(tid, uid, name, correct, total):
    await run("INSERT INTO results(test_id,user_id,name,correct,total,created) VALUES(?,?,?,?,?,?)",
              (tid, uid, name, correct, total, now()))


async def test_stats(tid):
    agg = await one("SELECT COUNT(*) AS n, AVG(correct*100.0/total) AS avg FROM results WHERE test_id=? AND total>0", (tid,))
    top = await fetch("""SELECT * FROM (
                           SELECT DISTINCT ON (user_id) name, correct AS c, total FROM results
                           WHERE test_id=? ORDER BY user_id, correct DESC) t
                         ORDER BY c DESC LIMIT 5""", (tid,))
    return agg, top


# ---------------- slayd resurslari (shablon / rasm) ----------------
async def add_asset(kind, name, keywords, file_id):
    return await insert("INSERT INTO assets(kind,name,keywords,file_id,created) VALUES(?,?,?,?,?)",
                        (kind, name, keywords, file_id, now()))


async def assets(kind):
    return await fetch("SELECT * FROM assets WHERE kind=? ORDER BY id", (kind,))


async def delete_asset(aid):
    await run("DELETE FROM assets WHERE id=?", (aid,))


# ---------------- so'z to'plamlari (o'yinlar uchun) ----------------
async def add_wordset(lang, title, pairs):
    sid = await insert("INSERT INTO wordsets(lang,title,created) VALUES(?,?,?)", (lang, title, now()))
    async with _pool.acquire() as c, c.transaction():
        await c.executemany("INSERT INTO words(set_id,word,translation) VALUES($1,$2,$3)",
                            [(sid, w, t) for w, t in pairs])
    return sid


async def wordsets():
    return await fetch("""SELECT s.*, (SELECT COUNT(*) FROM words w WHERE w.set_id=s.id) AS n
                          FROM wordsets s ORDER BY s.id DESC LIMIT 50""")


async def get_wordset(sid):
    return await one("SELECT * FROM wordsets WHERE id=?", (sid,))


async def wordset_words(sid):
    return await fetch("SELECT word, translation FROM words WHERE set_id=? ORDER BY id", (sid,))


async def delete_wordset(sid):
    async with _pool.acquire() as c, c.transaction():
        await c.execute("DELETE FROM words WHERE set_id=$1", sid)
        await c.execute("DELETE FROM wordsets WHERE id=$1", sid)
