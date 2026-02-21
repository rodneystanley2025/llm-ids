import os
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

DB_PATH = os.getenv("IDS_DB_PATH", "/data/ids.db")


def _conn() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def init_db() -> None:
    with _conn() as con:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS alerts (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              session_id TEXT NOT NULL,
              created_at TEXT NOT NULL,
              score INTEGER NOT NULL,
              severity TEXT NOT NULL,
              labels TEXT NOT NULL,
              top_reason TEXT NOT NULL,
              dedupe_key TEXT NOT NULL UNIQUE
            )
            """
        )
        con.commit()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def create_alert_if_needed(
    session_id: str,
    final_score: int,
    final_severity: str,
    labels: List[str],
    reasons: List[str],
    threshold: int,
) -> Optional[Dict[str, Any]]:
    """
    Create alert if score >= threshold.
    Dedupe on (session_id + top_reason) so repeated calls don't spam.
    """
    if int(final_score) < int(threshold):
        return None

    top_reason = (reasons[0] if reasons else "")
    labels_str = ",".join(labels)
    dedupe_key = f"{session_id}:{top_reason}"

    alert = {
        "session_id": session_id,
        "created_at": _now_iso(),
        "score": int(final_score),
        "severity": str(final_severity),
        "labels": labels,
        "top_reason": top_reason,
        "dedupe_key": dedupe_key,
    }

    with _conn() as con:
        try:
            con.execute(
                """
                INSERT INTO alerts (session_id, created_at, score, severity, labels, top_reason, dedupe_key)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    alert["session_id"],
                    alert["created_at"],
                    alert["score"],
                    alert["severity"],
                    labels_str,
                    alert["top_reason"],
                    alert["dedupe_key"],
                ),
            )
            con.commit()
            return alert
        except sqlite3.IntegrityError:
            # Duplicate dedupe_key => already alerted
            return None


def list_alerts(limit: int = 50) -> List[Dict[str, Any]]:
    with _conn() as con:
        rows = con.execute(
            "SELECT * FROM alerts ORDER BY id DESC LIMIT ?",
            (int(limit),),
        ).fetchall()

    out: List[Dict[str, Any]] = []
    for r in rows:
        out.append(
            {
                "id": r["id"],
                "session_id": r["session_id"],
                "created_at": r["created_at"],
                "score": r["score"],
                "severity": r["severity"],
                "labels": (r["labels"].split(",") if r["labels"] else []),
                "top_reason": r["top_reason"],
            }
        )
    return out
