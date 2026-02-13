import sqlite3
from pathlib import Path

DB_PATH = Path("/data/llm_ids.db")

def get_conn():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_conn()
    conn.execute("""
    CREATE TABLE IF NOT EXISTS events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id TEXT,
        turn_id INTEGER,
        role TEXT,
        content TEXT,
        ts TEXT,
        model TEXT
    )
    """)
    conn.commit()
    conn.close()

