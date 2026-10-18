"""BIR MARTALIK: eski bot.db (SQLite) dagi ma'lumotlarni Postgres'ga ko'chiradi.
Ishlatish:  python migrate_sqlite_to_pg.py bot.db
"""
import asyncio
import json
import sqlite3
import sys
import db


async def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "bot.db"
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    data = {}
    for t in db.TABLES:
        src = "usage" if t == "usage_log" else t
        try:
            data[t] = [dict(r) for r in con.execute(f"SELECT * FROM {src}")]
        except sqlite3.OperationalError:
            data[t] = []
    await db.init(seed=False)
    await db.import_json(json.dumps(data).encode())
    await db.seed_defaults()
    print({t: len(r) for t, r in data.items()})
    print("Ko'chirish tugadi ✅")
    await db.close()


asyncio.run(main())
