import os
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
from typing import Optional


DB_PATH = os.getenv("IDS_DB_PATH", "/data/ids.db")


def _conn() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _ensure_column(con: sqlite3.Connection, table: str, col: str, col_def: str) -> None:
    """
    SQLite doesn't support ALTER TABLE ADD COLUMN IF NOT EXISTS,
    so we check table_info and add only if missing.
    """
    cols = [r["name"] for r in con.execute(f"PRAGMA table_info({table})").fetchall()]
    if col not in cols:
        con.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_def}")


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
              dedupe_key TEXT NOT NULL UNIQUE,

              -- Enrichment fields (added later; init_db will also migrate older DBs)
              spike_turn INTEGER,
              spike_delta INTEGER,
              max_user_keyword_delta INTEGER,
              increase_turns TEXT,
              timeline_url TEXT
            )
            """
        )

        # Migrate older DBs (if table exists but columns don't)
        _ensure_column(con, "alerts", "spike_turn", "INTEGER")
        _ensure_column(con, "alerts", "spike_delta", "INTEGER")
        _ensure_column(con, "alerts", "max_user_keyword_delta", "INTEGER")
        _ensure_column(con, "alerts", "increase_turns", "TEXT")
        _ensure_column(con, "alerts", "timeline_url", "TEXT")

        con.commit()


def create_alert_if_needed(
    session_id: str,
    final_score: int,
    final_severity: str,
    labels: List[str],
    reasons: List[str],
    threshold: int,
    evidence: Optional[Dict[str, Any]] = None,
    timeline_url: Optional[str] = None,
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

    # Pull enrichment from velocity evidence if available
    risk_vel = (evidence or {}).get("risk_velocity", {}) if isinstance(evidence, dict) else {}

    spike_turn = risk_vel.get("spike_turn")
    spike_delta = risk_vel.get("spike_delta")
    max_user_keyword_delta = risk_vel.get("max_user_keyword_delta")
    increase_turns = risk_vel.get("increase_turns")

    if isinstance(increase_turns, list):
        increase_turns_str = ",".join(str(x) for x in increase_turns)
    else:
        increase_turns_str = ""

    tl_url = timeline_url or f"/v1/timeline/{session_id}"

    alert = {
        "session_id": session_id,
        "created_at": _now_iso(),
        "score": int(final_score),
        "severity": str(final_severity),
        "labels": labels,
        "top_reason": top_reason,
        "spike_turn": spike_turn,
        "spike_delta": spike_delta,
        "max_user_keyword_delta": max_user_keyword_delta,
        "increase_turns": (increase_turns if isinstance(increase_turns, list) else []),
        "timeline_url": tl_url,
        "dedupe_key": dedupe_key,
    }

    with _conn() as con:
        try:
            con.execute(
                """
                INSERT INTO alerts (
                  session_id, created_at, score, severity, labels, top_reason, dedupe_key,
                  spike_turn, spike_delta, max_user_keyword_delta, increase_turns, timeline_url
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    alert["session_id"],
                    alert["created_at"],
                    alert["score"],
                    alert["severity"],
                    labels_str,
                    alert["top_reason"],
                    alert["dedupe_key"],
                    alert["spike_turn"],
                    alert["spike_delta"],
                    alert["max_user_keyword_delta"],
                    ",".join(str(x) for x in alert["increase_turns"]),
                    alert["timeline_url"],
                ),
            )
            con.commit()
            return alert
        except sqlite3.IntegrityError:
            return None


def list_alerts(limit: int = 50) -> List[Dict[str, Any]]:
    with _conn() as con:
        rows = con.execute(
            "SELECT * FROM alerts ORDER BY id DESC LIMIT ?",
            (int(limit),),
        ).fetchall()

    out: List[Dict[str, Any]] = []
    for r in rows:
        inc = (r["increase_turns"] or "")
        out.append(
            {
                "id": r["id"],
                "session_id": r["session_id"],
                "created_at": r["created_at"],
                "score": r["score"],
                "severity": r["severity"],
                "labels": (r["labels"].split(",") if r["labels"] else []),
                "top_reason": r["top_reason"],
                # enrichment
                "spike_turn": r["spike_turn"],
                "spike_delta": r["spike_delta"],
                "max_user_keyword_delta": r["max_user_keyword_delta"],
                "increase_turns": ([int(x) for x in inc.split(",") if x.strip()] if inc else []),
                "timeline_url": r["timeline_url"] or f"/v1/timeline/{r['session_id']}",
            }
        )
    return out

def list_active_alerts(
    window_seconds: int = 600,
    limit: int = 50,
    min_score: int = 0,
    label: Optional[str] = None,
    severity: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Returns alerts created within the last `window_seconds`, newest first,
    optionally filtered by min_score, label, severity.
    """
    now = datetime.now(timezone.utc)
    cutoff = now.timestamp() - int(window_seconds)

    # Pull a bit more than limit, then filter in Python (avoids SQLite datetime quirks with Z timestamps)
    fetch_n = max(int(limit) * 5, 200)

    with _conn() as con:
        rows = con.execute(
            "SELECT * FROM alerts ORDER BY id DESC LIMIT ?",
            (fetch_n,),
        ).fetchall()

    out: List[Dict[str, Any]] = []
    for r in rows:
        created_at = r["created_at"] or ""
        try:
            # created_at like "2026-02-21T02:43:40.561484Z"
            dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        except Exception:
            continue

        if dt.timestamp() < cutoff:
            continue

        score = int(r["score"] or 0)
        if score < int(min_score):
            continue

        labels_list = (r["labels"].split(",") if r["labels"] else [])

        if label and label not in labels_list:
            continue
        if severity and str(r["severity"]) != str(severity):
            continue

        inc = (r["increase_turns"] or "")
        out.append(
            {
                "id": r["id"],
                "session_id": r["session_id"],
                "created_at": r["created_at"],
                "score": score,
                "severity": r["severity"],
                "labels": labels_list,
                "top_reason": r["top_reason"],
                "spike_turn": r["spike_turn"],
                "spike_delta": r["spike_delta"],
                "max_user_keyword_delta": r["max_user_keyword_delta"],
                "increase_turns": ([int(x) for x in inc.split(",") if x.strip()] if inc else []),
                "timeline_url": r["timeline_url"] or f"/v1/timeline/{r['session_id']}",
            }
        )

        if len(out) >= int(limit):
            break

    return out
