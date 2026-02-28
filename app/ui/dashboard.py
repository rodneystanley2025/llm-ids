from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from app.storage.db import list_sessions
from app.alerts.store import list_active_alerts

from app.ui.layout import page_html


router = APIRouter()


@router.get("/ui/dashboard", response_class=HTMLResponse)
def dashboard():

    sessions = list_sessions(limit=1000)

    total_sessions=len(sessions)

    active=list_active_alerts(3600)

    active_count=len(active)

    high=sum(1 for a in active if a["severity"]=="HIGH")
    medium=sum(1 for a in active if a["severity"]=="MEDIUM")
    low=sum(1 for a in active if a["severity"]=="LOW")
    critical=sum(1 for a in active if a["severity"]=="CRITICAL")

    rows="".join(f"""
<tr>
<td><code>{a["session_id"]}</code></td>
<td>{a["severity"]}</td>
<td>{round(a["confidence"]*100)}%</td>
</tr>
""" for a in active[:10])

    body=f"""
<h2>Operator Dashboard</h2>

<div class="card">

<b>Total Sessions:</b> {total_sessions}<br>

<b>Active Alerts:</b> {active_count}<br>

<b>Critical:</b> {critical} |
<b>High:</b> {high} |
<b>Medium:</b> {medium} |
<b>Low:</b> {low}

</div>

<div class="card">

<h3>Recent Active Alerts</h3>

<table>

<thead>

<tr>
<th>Session</th>
<th>Severity</th>
<th>Confidence</th>
</tr>

</thead>

<tbody>

{rows if rows else '<tr><td colspan=3>No Active Alerts</td></tr>'}

</tbody>

</table>

</div>
"""

    return page_html(
        "Dashboard",
        body,
        active="dashboard",
    )
