from __future__ import annotations

import sqlite3
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any

DB_PATH = Path("llm_ids.db")


# ---------------------------------------------------------
# CONNECTION
# ---------------------------------------------------------

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ---------------------------------------------------------
# INIT DB
# ---------------------------------------------------------

def init_db():
    conn = get_conn()

    # EVENTS
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

    # ALERTS
    conn.execute("""
    CREATE TABLE IF NOT EXISTS alerts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id TEXT,
        severity TEXT,
        score INTEGER,
        labels TEXT,
        confidence REAL,
        created_at TEXT
    )
    """)

    conn.commit()
    conn.close()


# ---------------------------------------------------------
# EVENTS
# ---------------------------------------------------------

def get_session_events(session_id: str) -> List[Dict[str, Any]]:
    conn = get_conn()

    rows = conn.execute(
        """
        SELECT *
        FROM events
        WHERE session_id = ?
        ORDER BY turn_id ASC
        """,
        (session_id,),
    ).fetchall()

    conn.close()
    return [dict(r) for r in rows]


def list_sessions(limit: int = 100):
    conn = get_conn()

    rows = conn.execute(
        """
        SELECT
            session_id,
            COUNT(*) as event_count
        FROM events
        GROUP BY session_id
        ORDER BY MAX(ts) DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()

    conn.close()
    return [dict(r) for r in rows]


# ---------------------------------------------------------
# ALERTS
# ---------------------------------------------------------

def insert_alert(
    session_id: str,
    severity: str,
    score: int,
    labels: List[str],
    confidence: float,
    created_at: str,
):
    conn = get_conn()

    conn.execute(
        """
        INSERT INTO alerts
        (session_id, severity, score, labels, confidence, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            session_id,
            severity,
            score,
            ",".join(labels),
            confidence,
            created_at,
        ),
    )

    conn.commit()
    conn.close()


def list_alerts(limit: int = 100):
    conn = get_conn()

    rows = conn.execute(
        """
        SELECT *
        FROM alerts
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()

    conn.close()

    alerts = []
    for r in rows:
        d = dict(r)
        d["labels"] = d.get("labels", "").split(",") if d.get("labels") else []
        alerts.append(d)

    return alerts


def get_alerts_for_session(session_id: str):
    conn = get_conn()

    rows = conn.execute(
        """
        SELECT *
        FROM alerts
        WHERE session_id = ?
        ORDER BY created_at DESC
        """,
        (session_id,),
    ).fetchall()

    conn.close()

    alerts = []
    for r in rows:
        d = dict(r)
        d["labels"] = d.get("labels", "").split(",") if d.get("labels") else []
        alerts.append(d)

    return alerts


# ---------------------------------------------------------
# ACTIVE ALERTS (🔥 THIS FIXES YOUR CRASH)
# ---------------------------------------------------------

def list_active_alerts(window_seconds: int = 3600):
    conn = get_conn()

    cutoff = datetime.now(timezone.utc) - timedelta(seconds=window_seconds)

    rows = conn.execute(
        """
        SELECT *
        FROM alerts
        WHERE created_at >= ?
        ORDER BY created_at DESC
        """,
        (cutoff.isoformat(),),
    ).fetchall()

    conn.close()

    alerts = []
    for r in rows:
        d = dict(r)
        d["labels"] = d.get("labels", "").split(",") if d.get("labels") else []
        alerts.append(d)

    return alerts


# ---------------------------------------------------------
# DEV RESET
# ---------------------------------------------------------

def dev_reset_all():
    conn = get_conn()
    conn.execute("DELETE FROM events")
    conn.execute("DELETE FROM alerts")
    conn.commit()
    conn.close()
