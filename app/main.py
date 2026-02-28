from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.schemas import Event
from app.scoring.timeline import build_timeline
from app.scoring.engine import score_session, config_snapshot
from app.storage.db import (
    get_conn,
    init_db as init_events_db,
    list_sessions,
    get_session_events,
    list_alerts,
    get_alerts_for_session,
    dev_reset_all,
)
from app.alerts.service import maybe_emit_alert
from app.ui.layout import page_html
from app.ui.dashboard import router as dashboard_router
from app.ui.alerts import router as alerts_router
from app.ui.active import router as active_router  # ✅ FIXED
from app.alerts.store import init_db as init_alerts_db

# ---------------------------------------------------------
# Helpers
# ---------------------------------------------------------

def utc_now_iso():
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
    )


@asynccontextmanager
async def lifespan(_: FastAPI):

    init_events_db()

    init_alerts_db()   # ⭐ REQUIRED

    yield


app = FastAPI(
    title="LLM‑IDS",
    version="0.6.0",
    lifespan=lifespan,
)

# ---------------------------------------------------------
# ROUTERS
# ---------------------------------------------------------

app.include_router(dashboard_router)
app.include_router(alerts_router)
app.include_router(active_router)   # ✅ FIXED


# ---------------------------------------------------------
# Health
# ---------------------------------------------------------

@app.get("/health")
def health():
    return {"ok": True}


# ---------------------------------------------------------
# DEV RESET (Toast Enabled)
# ---------------------------------------------------------

@app.post("/ui/dev/reset")
def ui_dev_reset():
    dev_reset_all()
    return RedirectResponse(
        "/ui/dashboard?msg=System+Reset+Complete",
        status_code=303,
    )


# ---------------------------------------------------------
# Events ingest (API)
# ---------------------------------------------------------

@app.post("/v1/events")
def ingest_event(evt: Event):

    ts = evt.ts or utc_now_iso()

    conn = get_conn()
    conn.execute(
        """
        INSERT INTO events
        (session_id, turn_id, role, content, ts, model)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            evt.session_id,
            evt.turn_id,
            evt.role,
            evt.content,
            ts,
            evt.model,
        ),
    )
    conn.commit()
    conn.close()

    events = get_session_events(evt.session_id)
    result = score_session(events)

    maybe_emit_alert(evt.session_id, result)

    return {"received": True}


# ---------------------------------------------------------
# Alerts API
# ---------------------------------------------------------

@app.get("/v1/alerts")
def alerts(limit: int = 100):
    return {"alerts": list_alerts(limit=limit)}


@app.get("/v1/alerts/{session_id}")
def alerts_session(session_id: str):
    return {
        "session_id": session_id,
        "alerts": get_alerts_for_session(session_id),
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
def ui_home(request: Request):

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
# UI SEND
# ---------------------------------------------------------

@app.post("/ui/send")
def ui_send(
    session_id: str = Form(default=""),
    content: str = Form(default=""),
):

    sid = session_id.strip()

    if not sid:
        sid = f"ui_{int(datetime.now(timezone.utc).timestamp())}"

    events = get_session_events(sid)
    turn = 1

    if events:
        turn = max(int(e["turn_id"]) for e in events) + 1

    conn = get_conn()
    conn.execute(
        """
        INSERT INTO events
        (session_id, turn_id, role, content, ts, model)
        VALUES (?, ?, ?, ?, ?, ?)
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

    result = score_session(get_session_events(sid))
    maybe_emit_alert(sid, result)

    return RedirectResponse("/ui/sessions", status_code=303)


# ---------------------------------------------------------
# Sessions UI
# ---------------------------------------------------------

@app.get("/ui/sessions", response_class=HTMLResponse)
def ui_sessions(request: Request, limit: int = 100):

    items = list_sessions(limit=limit)

    rows = []

    for s in items:
        sid = s.get("session_id", "")
        cnt = s.get("event_count", 0)

        rows.append(f"""
        <tr>
            <td><code>{sid}</code></td>
            <td>{cnt}</td>
            <td>
                <a href="/ui/timeline/{sid}">Timeline</a>
            </td>
        </tr>
        """)

    body = f"""
    <h2>Sessions</h2>
    <div class="card">
        <table>
            <thead>
                <tr>
                    <th>Session</th>
                    <th>Events</th>
                    <th></th>
                </tr>
            </thead>
            <tbody>
                {''.join(rows) if rows else '<tr><td colspan="3">No Sessions</td></tr>'}
            </tbody>
        </table>
    </div>
    """

    return page_html("Sessions", body, active="sessions", request=request)


# ---------------------------------------------------------
# Timeline UI
# ---------------------------------------------------------

@app.get("/ui/timeline/{session_id}", response_class=HTMLResponse)
def ui_timeline(session_id: str, request: Request):

    events = get_session_events(session_id)

    if not events:
        raise HTTPException(status_code=404, detail="session not found")

    tl = build_timeline(events, include_events=True)
    final = tl.get("final", {})

    body = f"""
    <h2>Timeline — {session_id}</h2>

    <div class="card">
        <b>Severity:</b> {final.get("severity")}<br>
        <b>Score:</b> {final.get("score")}<br>
        <b>Confidence:</b> {final.get("confidence")}
    </div>
    """

    return page_html(
        f"Timeline {session_id}",
        body,
        active="sessions",
        request=request,
    )
