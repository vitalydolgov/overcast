import sqlite3
import os
from contextlib import closing

DB_PATH = os.path.join(os.path.dirname(__file__), "overcast.db")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.execute(
        "CREATE TABLE IF NOT EXISTS cloudy_days (day TEXT PRIMARY KEY, cloudy INTEGER NOT NULL)"
    )
    conn.commit()
    conn.close()
