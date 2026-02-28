from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from app.storage.db import list_sessions
from app.ui.layout import page_html
from app.alerts.store import list_active_alerts

router = APIRouter()

@router.get("/ui/active", response_class=HTMLResponse)
def active_view(window_seconds: int = 3600):

    alerts = list_active_alerts(window_seconds=window_seconds)

    rows = []

    for a in alerts:
        rows.append(f"""
        <tr>
        <td><code>{a.get("session_id")}</code></td>
        <td>{a.get("severity")}</td>
        <td>{a.get("confidence")}</td>
        </tr>
        """)

    body = f"""
    <h2>Active Alerts (Last {window_seconds} sec)</h2>
    <div class="card">
    <table>
    <thead>
    <tr><th>Session</th><th>Severity</th><th>Confidence</th></tr>
    </thead>
    <tbody>
    {''.join(rows) if rows else '<tr><td colspan="3">No Active Alerts</td></tr>'}
    </tbody>
    </table>
    </div>
    """

    return page_html("Active Alerts", body, active="active")

@router.get("/ui/dashboard", response_class=HTMLResponse)
def dashboard():

    sessions = list_sessions(limit=1000)
    total = len(sessions)

    body = f"""
    <h2>Dashboard</h2>
    <div class="card">
    <b>Total Sessions:</b> {total}
    </div>
    """

    return page_html("Dashboard", body, active="dashboard")
