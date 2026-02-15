from typing import List, Dict, Any
import sqlite3
from pathlib import Path
import json

DB_PATH = Path("/data/llm_ids.db")


def get_conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = get_conn()

    # Events table
    conn.execute("""
    CREATE TABLE IF NOT EXISTS events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id TEXT NOT NULL,
        turn_id INTEGER NOT NULL,
        role TEXT NOT NULL,
        content TEXT NOT NULL,
        ts TEXT,
        model TEXT
    )
    """)

    # Prevent duplicates for the same turn+role within a session
    conn.execute("""
    CREATE UNIQUE INDEX IF NOT EXISTS ux_events_session_turn_role
    ON events(session_id, turn_id, role)
    """)

    # Alerts table
    conn.execute("""
    CREATE TABLE IF NOT EXISTS alerts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id TEXT NOT NULL,
        ts TEXT NOT NULL,
        alert_type TEXT NOT NULL,
        severity TEXT NOT NULL,
        confidence REAL NOT NULL,
        reasons TEXT NOT NULL,     -- JSON string
        evidence TEXT NOT NULL     -- JSON string
    )
    """)

    # Dedupe alerts: same session + type + evidence shouldn't spam
    conn.execute("""
    CREATE UNIQUE INDEX IF NOT EXISTS ux_alerts_session_type_evidence
    ON alerts(session_id, alert_type, evidence)
    """)

    conn.commit()
    conn.close()


def list_sessions(limit: int = 50) -> List[Dict[str, Any]]:
    conn = get_conn()
    rows = conn.execute(
        """
        SELECT session_id,
               MIN(ts) AS first_ts,
               MAX(ts) AS last_ts,
               COUNT(*) AS event_count
        FROM events
        GROUP BY session_id
        ORDER BY last_ts DESC
        LIMIT ?
        """,
        (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_session_events(session_id: str) -> List[Dict[str, Any]]:
    conn = get_conn()
    rows = conn.execute(
        """
        SELECT id, session_id, turn_id, role, content, ts, model
        FROM events
        WHERE session_id = ?
        ORDER BY turn_id ASC, id ASC
        """,
        (session_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def insert_alert(
    session_id: str,
    ts: str,
    alert_type: str,
    severity: str,
    confidence: float,
    reasons: list,
    evidence: dict,
) -> None:
    conn = get_conn()
    conn.execute(
        """
        INSERT OR IGNORE INTO alerts (session_id, ts, alert_type, severity, confidence, reasons, evidence)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            session_id,
            ts,
            alert_type,
            severity,
            float(confidence),
            json.dumps(reasons),
            json.dumps(evidence),
        )
    )
    conn.commit()
    conn.close()


def list_alerts(limit: int = 50) -> List[Dict[str, Any]]:
    conn = get_conn()
    rows = conn.execute(
        """
        SELECT id, session_id, ts, alert_type, severity, confidence, reasons, evidence
        FROM alerts
        ORDER BY id DESC
        LIMIT ?
        """,
        (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_alerts_for_session(session_id: str) -> List[Dict[str, Any]]:
    conn = get_conn()
    rows = conn.execute(
        """
        SELECT id, session_id, ts, alert_type, severity, confidence, reasons, evidence
        FROM alerts
        WHERE session_id = ?
        ORDER BY id DESC
        """,
        (session_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
