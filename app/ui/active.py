from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from app.alerts.store import list_active_alerts
from app.ui.layout import page_html

router = APIRouter()


@router.get("/ui/active", response_class=HTMLResponse)
def ui_active():

    alerts = list_active_alerts(3600)

    rows = []

    for a in alerts:

        rows.append(f"""
<tr>
<td><code>{a.get("session_id")}</code></td>
<td>{a.get("severity")}</td>
<td>{a.get("score")}</td>
<td>{round((a.get("confidence") or 0)*100)}%</td>
</tr>
""")

    body=f"""
<h2>Active Alerts (Last Hour)</h2>

<div class="card">

<table>

<thead>

<tr>
<th>Session</th>
<th>Severity</th>
<th>Score</th>
<th>Confidence</th>
</tr>

</thead>

<tbody>

{''.join(rows) if rows else '<tr><td colspan=4>No Active Alerts</td></tr>'}

</tbody>

</table>

</div>
"""

    return page_html(
        "Active Alerts",
        body,
        active="active",
    )
