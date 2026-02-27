from typing import List, Dict, Any

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from app.alerts.store import list_active_alerts, list_alerts
from app.ui.layout import page_html


router = APIRouter()


# ---------------------------------------------------------
# helpers
# ---------------------------------------------------------
def esc(s: str) -> str:
    return (
        (s or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def severity_color(sev: str) -> str:
    return {
        "NONE": "#64748b",
        "LOW": "#0ea5e9",
        "MED": "#f59e0b",
        "HIGH": "#ef4444",
    }.get((sev or "NONE").upper(), "#64748b")


# =========================================================
# LIVE DASHBOARD
# =========================================================
@router.get("/ui/dashboard", response_class=HTMLResponse)
def ui_dashboard(window_seconds: int = 3600, limit: int = 100):

    alerts: List[Dict[str, Any]] = list_active_alerts(
        window_seconds=window_seconds,
        limit=limit,
    )

    rows = []

    for a in alerts:

        sid = a.get("session_id", "")

        severity = a.get("severity") or "NONE"
        score = int(a.get("score") or 0)

        labels = ", ".join(a.get("labels") or [])

        pill = severity_color(severity)

        rows.append(
            f"""
<tr>
<td class="session-id" title="{esc(sid)}">
<code>{esc(sid)}</code>
</td>

<td>
<span class="pill" style="background:{pill}">
{esc(severity)}
</span>
</td>

<td style="text-align:right;">
{score}
</td>

<td>
{esc(labels) or "—"}
</td>

<td class="links">

<a href="/ui/timeline/{esc(sid)}">Timeline</a>

<a href="/ui/alerts/{esc(sid)}">
Alerts
</a>

</td>

</tr>
"""
        )

    body = f"""
<h2>🔥 Live Risk Dashboard</h2>

<div class="card">

<div class="muted">
Auto refresh every 10 seconds
</div>

</div>

<div class="card">

<table>

<thead>
<tr>

<th>Session</th>
<th>Severity</th>
<th style="text-align:right;">Score</th>
<th>Labels</th>
<th>Links</th>

</tr>
</thead>

<tbody>

{''.join(rows) if rows else '<tr><td colspan="5" class="muted">No active alerts.</td></tr>'}

</tbody>

</table>

</div>
"""

    extra_head = """
<meta http-equiv="refresh" content="10">
"""

    extra_css = """
.pill{
color:white;
padding:4px 10px;
border-radius:999px;
font-weight:600;
}
"""

    return page_html(
        "Live Dashboard",
        body,
        active="dashboard",
        extra_head=extra_head,
        extra_css=extra_css,
    )


# =========================================================
# ACTIVE UI PAGE ⭐ (THIS FIXES YOUR ERROR)
# =========================================================
@router.get("/ui/active", response_class=HTMLResponse)
def ui_active(window_seconds: int = 3600, limit: int = 100):

    alerts = list_active_alerts(
        window_seconds=window_seconds,
        limit=limit,
    )

    rows = []

    for a in alerts:

        sid = a.get("session_id", "")

        rows.append(
            f"""
<tr>

<td class="session-id" title="{esc(sid)}">

<code>{esc(sid)}</code>

</td>

<td>

<a href="/ui/timeline/{esc(sid)}">
Timeline
</a>

</td>

<td>

<a href="/ui/alerts/{esc(sid)}">
Alerts
</a>

</td>

</tr>
"""
        )

    body = f"""
<h2>⚡ Active Sessions</h2>

<div class="card">

<table>

<thead>

<tr>

<th>Session</th>
<th>Timeline</th>
<th>Alerts</th>

</tr>

</thead>

<tbody>

{''.join(rows) if rows else '<tr><td colspan="3" class="muted">No active sessions.</td></tr>'}

</tbody>

</table>

</div>
"""

    return page_html(
        "Active Sessions",
        body,
        active="active",
    )


# =========================================================
# ALERTS LIST PAGE
# =========================================================
@router.get("/ui/alerts", response_class=HTMLResponse)
def ui_alerts(limit: int = 100):

    alerts = list_alerts(limit=limit)

    rows = []

    for a in alerts:

        sid = a.get("session_id", "")

        rows.append(
            f"""
<tr>

<td class="session-id" title="{esc(sid)}">

<code>{esc(sid)}</code>

</td>

<td>

{esc(a.get("severity",""))}

</td>

<td>

<a href="/ui/alerts/{esc(sid)}">

View

</a>

</td>

</tr>
"""
        )

    body = f"""
<h2>🚨 Alerts</h2>

<div class="card">

<table>

<thead>

<tr>

<th>Session</th>
<th>Severity</th>
<th>View</th>

</tr>

</thead>

<tbody>

{''.join(rows) if rows else '<tr><td colspan="3">No alerts.</td></tr>'}

</tbody>

</table>

</div>
"""

    return page_html(
        "Alerts",
        body,
        active="alerts",
    )
