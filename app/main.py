from contextlib import asynccontextmanager
from datetime import datetime, timezone
import re

from fastapi import FastAPI, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse

from app.schemas import Event
from app.scoring.timeline import build_timeline
from app.storage.db import (
    get_conn,
    init_db as init_events_db,
    list_sessions,
    get_session_events,
    insert_alert,
    get_alerts_for_session,
)
from app.alerts.store import (
    init_db as init_alerts_db,
    list_alerts,
    list_active_alerts,
)
from app.alerts.service import maybe_emit_alert
from app.scoring.engine import score_session, config_snapshot

from app.ui.alerts import router as alerts_router
from app.ui.dashboard import router as dashboard_router
from app.ui.layout import page_html


# ---------------------------------------------------------
# SESSION ID POLICY ⭐⭐⭐⭐⭐
# ---------------------------------------------------------

SESSION_ID_MAX = 64

SESSION_RE = re.compile(r"[^a-zA-Z0-9_\-]+")


def normalize_session_id(raw: str) -> str:
    """
    Senior engineer policy:

    - trim whitespace
    - replace spaces/symbols with _
    - limit length
    - never crash UI
    """

    sid = (raw or "").strip()

    if not sid:
        return f"ui_{int(datetime.now(timezone.utc).timestamp())}"

    # replace bad characters
    sid = SESSION_RE.sub("_", sid)

    # collapse multiple underscores
    sid = re.sub(r"_+", "_", sid)

    return sid[:SESSION_ID_MAX]


# ---------------------------------------------------------
# Helpers
# ---------------------------------------------------------

def utc_now_iso():
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_events_db()
    init_alerts_db()
    yield


app = FastAPI(
    title="LLM‑IDS",
    version="0.6.0",
    lifespan=lifespan,
)

app.include_router(dashboard_router)
app.include_router(alerts_router)


# ---------------------------------------------------------
# Health
# ---------------------------------------------------------

@app.get("/health")
def health():
    return {"ok": True}


# ---------------------------------------------------------
# Events ingest API
# ---------------------------------------------------------

@app.post("/v1/events")
def ingest_event(evt: Event):

    sid = normalize_session_id(evt.session_id)

    ts = evt.ts or utc_now_iso()

    conn = get_conn()

    conn.execute(
        """
        INSERT INTO events
        (session_id,turn_id,role,content,ts,model)
        VALUES (?,?,?,?,?,?)
        """,
        (
            sid,
            evt.turn_id,
            evt.role,
            evt.content,
            ts,
            evt.model,
        ),
    )

    conn.commit()
    conn.close()

    events = get_session_events(sid)

    result = score_session(events)

    maybe_emit_alert(sid, result)

    for label in result.get("labels", []):

        insert_alert(
            session_id=sid,
            ts=ts,
            alert_type=label,
            severity=result["severity"],
            confidence=result["score"] / 100.0,
            reasons=result.get("reasons", {}),
            evidence=result.get("evidence", {}),
        )

    return {"received": True}


# ---------------------------------------------------------
# Alerts API
# ---------------------------------------------------------

@app.get("/v1/alerts")
def alerts(limit: int = 100):
    return {"alerts": list_alerts(limit=limit)}


@app.get("/v1/alerts/{session_id}")
def alerts_session(session_id: str):

    sid = normalize_session_id(session_id)

    alerts = get_alerts_for_session(sid)

    return {
        "session_id": sid,
        "alerts": alerts,
    }


@app.get("/v1/active")
def active_feed(window_seconds: int = 3600):
    return {
        "window_seconds": window_seconds,
        "active": list_active_alerts(window_seconds=window_seconds),
    }


# ---------------------------------------------------------
# Config
# ---------------------------------------------------------

@app.get("/v1/config")
def config():
    return config_snapshot()


# ---------------------------------------------------------
# UI HOME
# ---------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
def ui_home():

    body = """
<h2>LLM IDS</h2>

<div class="card">

<form method="post" action="/ui/send">

<label>Session ID</label>

<input name="session_id"
style="width:100%;padding:10px;margin-top:6px;">

<label>Message</label>

<textarea name="content"
rows="6"
style="width:100%;padding:10px;margin-top:6px;"></textarea>

<button type="submit"
style="margin-top:12px;">

Send

</button>

</form>

</div>
"""

    return page_html("Home", body, active="home")


@app.post("/ui/send")
def ui_send(
    session_id: str = Form(default=""),
    content: str = Form(default=""),
):

    sid = normalize_session_id(session_id)

    events = get_session_events(sid)

    turn = 1

    if events:
        turn = max(int(e["turn_id"]) for e in events) + 1

    conn = get_conn()

    conn.execute(
        """
        INSERT INTO events
        (session_id,turn_id,role,content,ts,model)
        VALUES (?,?,?,?,?,?)
        """,
        (
            sid,
            turn,
            "user",
            content,
            utc_now_iso(),
            None,
        ),
    )

    conn.commit()
    conn.close()

    maybe_emit_alert(
        sid,
        score_session(get_session_events(sid)),
    )

    return RedirectResponse(
        "/ui/sessions",
        status_code=303,
    )


# ---------------------------------------------------------
# Sessions UI
# ---------------------------------------------------------

@app.get("/ui/sessions", response_class=HTMLResponse)
def ui_sessions(limit: int = 100, q: str = ""):

    items = list_sessions(limit=limit)

    qn = (q or "").lower().strip()

    if qn:
        items = [
            s for s in items
            if qn in (s.get("session_id", "").lower())
        ]

    def esc(s: str) -> str:
        return (
            (s or "")
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )

    rows = []

    for s in items:

        sid = s.get("session_id", "")

        first = s.get("first_ts") or "—"
        last = s.get("last_ts") or "—"

        cnt = int(s.get("event_count") or 0)

        short = sid[:22] + ("…" if len(sid) > 22 else "")

        rows.append(
f"""
<tr>
<td title="{esc(sid)}"><code>{esc(short)}</code></td>
<td>{esc(first)}</td>
<td>{esc(last)}</td>
<td style="text-align:right">{cnt}</td>
<td>
<a href="/ui/timeline/{esc(sid)}">Timeline</a>
<a href="/ui/alerts/{esc(sid)}">Alerts</a>
</td>
</tr>
"""
        )

    body = f"""
<h2>Sessions</h2>

<div class="card">

<table>

<thead>
<tr>
<th>Session</th>
<th>First Seen</th>
<th>Last Seen</th>
<th style="text-align:right">Events</th>
<th>Links</th>
</tr>
</thead>

<tbody>

{''.join(rows) if rows else '<tr><td colspan="5">No Sessions</td></tr>'}

</tbody>

</table>

</div>
"""

    return page_html(
        "Sessions",
        body,
        active="sessions",
    )


# ---------------------------------------------------------
# Timeline UI
# ---------------------------------------------------------

@app.get("/ui/timeline/{session_id}",
response_class=HTMLResponse)
def ui_timeline(session_id: str):

    sid = normalize_session_id(session_id)

    events = get_session_events(sid)

    if not events:
        raise HTTPException(
            status_code=404,
            detail="session_id not found",
        )

    tl = build_timeline(
        events,
        include_events=True,
        truncate=400,
    )

    final = tl.get("final", {})

    def esc(s: str):
        return (
            (s or "")
            .replace("&","&amp;")
            .replace("<","&lt;")
            .replace(">","&gt;")
        )

    rows = []

    for t in tl.get("turns", []):

        tid = t.get("turn_id")

        ev_html = []

        for e in t.get("events", []):

            role = esc(e.get("role",""))
            content = esc(e.get("content",""))

            ev_html.append(
                f"<div><b>{role}</b><pre>{content}</pre></div>"
            )

        rows.append(
f"""
<div class="card">

<b>Turn {tid}</b>

{''.join(ev_html)}

</div>
"""
        )

    body = f"""
<h2>Timeline — {esc(sid)}</h2>

<div class="card">

<b>Severity:</b> {esc(final.get("severity","NONE"))}<br>

<b>Score:</b> {int(final.get("score",0))}<br>

<b>Labels:</b> {esc(', '.join(final.get("labels",[])))}

</div>

{''.join(rows)}
"""

    return page_html(
        f"Timeline {sid}",
        body,
        active="sessions",
    )
