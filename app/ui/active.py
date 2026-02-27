# Active Feed Page
from typing import List, Dict, Any

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from app.alerts.store import list_active_alerts
from app.ui.layout import page_html


router = APIRouter()


def esc(s: str):

    return (
        (s or "")
        .replace("&","&amp;")
        .replace("<","&lt;")
        .replace(">","&gt;")
    )


@router.get("/ui/active", response_class=HTMLResponse)
def ui_active(window_seconds: int = 3600):

    alerts: List[Dict[str,Any]] = list_active_alerts(
        window_seconds=window_seconds
    )

    rows = []

    for a in alerts:

        sid = a.get("session_id","")

        sev = a.get("severity","NONE")

        rows.append(
f"""
<tr>

<td><code>{esc(sid)}</code></td>

<td>{esc(sev)}</td>

<td>

<a href="/ui/dashboard">Dashboard</a>

</td>

</tr>
"""
        )

    body = f"""

<h2>Active Alerts Feed</h2>

<div class="card">

<table>

<thead>

<tr>

<th>Session</th>

<th>Severity</th>

<th>Links</th>

</tr>

</thead>

<tbody>

{''.join(rows) if rows else '<tr><td colspan=3>No active alerts</td></tr>'}

</tbody>

</table>

</div>
"""

    return page_html(
        "Active Feed",
        body,
        active="active",
    )
