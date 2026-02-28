from pathlib import Path
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any


DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

DB_PATH = DATA_DIR / "llm_ids.db"


def get_conn():

    conn = sqlite3.connect(DB_PATH)

    conn.row_factory = sqlite3.Row

    return conn


# ---------------------------------------------------------
# INIT DB
# ---------------------------------------------------------
def init_db():

    conn = get_conn()

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS alerts (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            session_id TEXT,

            created_at TEXT,

            alert_type TEXT,

            severity TEXT,

            score INTEGER,

            confidence REAL,

            evidence TEXT
        )
        """
    )

    conn.commit()
    conn.close()


# ---------------------------------------------------------
# INSERT
# ---------------------------------------------------------
def insert_alert(
    session_id: str,
    ts: str,
    alert_type: str,
    severity: str,
    score: int,
    confidence: float,
    evidence: Dict[str, Any],
):

    conn = get_conn()

    conn.execute(
        """
        INSERT INTO alerts
        (session_id,created_at,alert_type,severity,score,confidence,evidence)
        VALUES (?,?,?,?,?,?,?)
        """,
        (
            session_id,
            ts,
            alert_type,
            severity,
            score,
            confidence,
            str(evidence),
        ),
    )

    conn.commit()
    conn.close()


# ---------------------------------------------------------
# LIST ALERTS
# ---------------------------------------------------------
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

    return [dict(r) for r in rows]


# ---------------------------------------------------------
# ACTIVE ALERTS
# ---------------------------------------------------------
def list_active_alerts(window_seconds: int = 3600):

    conn = get_conn()

    cutoff = datetime.now(timezone.utc) - timedelta(
        seconds=window_seconds
    )

    rows = conn.execute(
        """
        SELECT *
        FROM alerts
        WHERE created_at >= ?
        ORDER BY created_at DESC
        """,
        (
            cutoff.isoformat().replace("+00:00", "Z"),
        ),
    ).fetchall()

    conn.close()

    return [dict(r) for r in rows]
