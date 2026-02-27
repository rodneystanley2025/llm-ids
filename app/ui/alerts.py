from typing import List, Dict, Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse

from app.alerts.store import list_alerts
from app.ui.layout import page_html


router = APIRouter()


def esc(s: str) -> str:
    return (
        (s or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


@router.get("/ui/alerts", response_class=HTMLResponse)
def alerts_page():

    alerts: List[Dict[str, Any]] = list_alerts(limit=200)

    rows = []

    for a in alerts:

        sid = a["session_id"]

        rows.append(f"""
<tr>

<td><code>{esc(sid)}</code></td>

<td>{esc(a.get("severity"))}</td>

<td>{a.get("score")}</td>

<td>{esc(", ".join(a.get("labels",[]) or []))}</td>

<td>

<a href="/ui/alerts/{esc(sid)}">View</a>

</td>

</tr>
""")

    body = f"""
<h2>Alerts</h2>

<div class="card">

<table>

<thead>

<tr>
<th>Session</th>
<th>Severity</th>
<th>Score</th>
<th>Labels</th>
<th>View</th>
</tr>

</thead>

<tbody>

{''.join(rows) if rows else "<tr><td colspan=5>No Alerts</td></tr>"}

</tbody>

</table>

</div>
"""

    return page_html(
        "Alerts",
        body,
        active="alerts",
    )


@router.get("/ui/alerts/{session_id}", response_class=HTMLResponse)
def alerts_for_session(session_id: str):

    alerts = [
        a for a in list_alerts(500)
        if a["session_id"] == session_id
    ]

    if not alerts:

        body = f"""
<h2>No Alerts</h2>

<div class="card">

No alerts exist for
<code>{esc(session_id)}</code>

</div>
"""

        return page_html(
            "No Alerts",
            body,
            active="alerts",
        )

    rows = []

    for a in alerts:

        rows.append(f"""
<tr>

<td>{a.get("created_at")}</td>

<td>{a.get("severity")}</td>

<td>{a.get("score")}</td>

<td>{esc(", ".join(a.get("labels",[])))}</td>

<td>
<a href="/ui/timeline/{esc(session_id)}">
Timeline
</a>
</td>

</tr>
""")

    body = f"""
<h2>Alerts : <code>{esc(session_id)}</code></h2>

<div class="card">

<table>

<thead>

<tr>
<th>Time</th>
<th>Severity</th>
<th>Score</th>
<th>Labels</th>
<th>Timeline</th>
</tr>

</thead>

<tbody>

{''.join(rows)}

</tbody>

</table>

</div>
"""

    return page_html(
        "Alerts",
        body,
        active="alerts",
    )
