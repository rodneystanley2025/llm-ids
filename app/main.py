from contextlib import asynccontextmanager
from datetime import datetime, timezone
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
    reset_all,
)
from app.alerts.store import (
    init_db as init_alerts_db,
    list_alerts,
    list_active_alerts,
)
from app.alerts.service import maybe_emit_alert
from app.scoring.engine import score_session, config_snapshot
from app.ui.alerts import router as alerts_router
from app.ui.layout import page_html
from app.ui.dashboard import router as dashboard_router
from app.storage.db import reset_all


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

def normalize_session_id(sid: str) -> str:
    sid = (sid or "").strip().replace(" ", "_")
    return sid[:64]

@asynccontextmanager
async def lifespan(_: FastAPI):
    init_events_db()
    init_alerts_db()
    yield

app = FastAPI(title="LLM‑IDS", version="0.6.0", lifespan=lifespan)

app.include_router(dashboard_router)
app.include_router(alerts_router)

# ---------------------------------------------------------
# DEV RESET
# ---------------------------------------------------------

@app.post("/dev/reset")
def dev_reset():
    reset_all()
    return {"status": "reset complete"}

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
            <input name="session_id" style="width:100%;padding:10px;margin-top:6px;">
            <label>Message</label>
            <textarea name="content" rows="6"
             style="width:100%;padding:10px;margin-top:6px;"></textarea>
            <button type="submit" style="margin-top:12px;">Send</button>
        </form>
    </div>
    """

    return page_html("Home", body, active="home")

# ---------------------------------------------------------
# SEND
# ---------------------------------------------------------

@app.post("/ui/send")
def ui_send(session_id: str = Form(default=""), content: str = Form(default="")):

    sid = normalize_session_id(session_id)

    if not sid:
        sid = f"ui_{int(datetime.now(timezone.utc).timestamp())}"

    events = get_session_events(sid)
    turn = 1
    if events:
        turn = max(int(e["turn_id"]) for e in events) + 1

    conn = get_conn()
    conn.execute(
        """
        INSERT INTO events (session_id,turn_id,role,content,ts,model)
        VALUES (?,?,?,?,?,?)
        """,
        (sid, turn, "user", content, utc_now_iso(), None),
    )
    conn.commit()
    conn.close()

    result = score_session(get_session_events(sid))
    maybe_emit_alert(sid, result)

    return RedirectResponse("/ui/sessions", status_code=303)

# ---------------------------------------------------------
# SESSIONS
# ---------------------------------------------------------

@app.get("/ui/sessions", response_class=HTMLResponse)
def ui_sessions(limit: int = 100):

    items = list_sessions(limit=limit)

    rows = []

    for s in items:
        sid = s.get("session_id", "")
        rows.append(
            f"""
            <tr>
            <td><code>{sid}</code></td>
            <td><a href="/ui/timeline/{sid}">Timeline</a></td>
            <td><a href="/ui/alerts/{sid}">Alerts</a></td>
            </tr>
            """
        )

    body = f"""
    <h2>Sessions</h2>
    <div class="card">
    <table>
    <thead>
    <tr><th>Session</th><th colspan="2">Links</th></tr>
    </thead>
    <tbody>
    {''.join(rows) if rows else '<tr><td colspan="3">No Sessions</td></tr>'}
    </tbody>
    </table>
    </div>
    """

    return page_html("Sessions", body, active="sessions")

# ---------------------------------------------------------
# TIMELINE
# ---------------------------------------------------------

@app.get("/ui/timeline/{session_id}", response_class=HTMLResponse)
def ui_timeline(session_id: str):

    events = get_session_events(session_id)
    if not events:
        raise HTTPException(status_code=404, detail="session_id not found")

    tl = build_timeline(events, include_events=True, truncate=400)
    final = tl.get("final", {})

    rows = []
    for t in tl.get("turns", []):
        tid = t.get("turn_id")
        ev_html = []
        for e in t.get("events", []):
            role = e.get("role", "")
            content = e.get("content", "")
            ev_html.append(f"<div><b>{role}</b><pre>{content}</pre></div>")
        rows.append(f"<div class='card'><b>Turn {tid}</b>{''.join(ev_html)}</div>")

    body = f"""
    <h2>Timeline — {session_id}</h2>
    <div class="card">
    <b>Severity:</b> {final.get("severity","NONE")}<br>
    <b>Risk Tier:</b> <span class="{final.get("risk_tier","NONE")}">
    {final.get("risk_tier","NONE")}</span><br>
    <b>Score:</b> {final.get("score",0)}<br>
    <b>Confidence:</b> {final.get("confidence",0.0)}<br>
    <b>Labels:</b> {', '.join(final.get("labels",[]))}
    </div>
    {''.join(rows)}
    """

    return page_html("Timeline", body, active="sessions")
