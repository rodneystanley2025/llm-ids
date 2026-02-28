from fastapi import APIRouter
from fastapi.responses import HTMLResponse, JSONResponse

from app.alerts.store import list_active_alerts
from app.ui.layout import page_html

router = APIRouter()


# ---------------------------------------------------------
# HTML PAGE
# ---------------------------------------------------------

@router.get("/ui/active", response_class=HTMLResponse)
def ui_active():

    body = """
<h2>Active Alerts (Live)</h2>

<div class="card">

<table id="activeTable">

<thead>
<tr>
<th>Session</th>
<th>Severity</th>
<th>Score</th>
<th>Confidence</th>
</tr>
</thead>

<tbody>

<tr>
<td colspan="4">
Loading Active Alerts...
</td>
</tr>

</tbody>

</table>

</div>


<script>

async function loadActive(){

    try{

        const res = await fetch("/api/active");

        const data = await res.json();

        const tbody =
            document.querySelector(
                "#activeTable tbody"
            );

        tbody.innerHTML="";

        if(!data.length){

            tbody.innerHTML=
            `<tr>
             <td colspan="4">
             No Active Alerts
             </td>
             </tr>`;

            return;
        }

        data.forEach(a=>{

            tbody.innerHTML+=`
<tr>

<td>
<code>${a.session_id}</code>
</td>

<td>${a.severity}</td>

<td>${a.score}</td>

<td>${a.confidence}</td>

</tr>
`;

        });

    }
    catch(e){

        console.error(e);

    }

}


loadActive();

setInterval(loadActive,5000);

</script>
"""

    return page_html(
        "Active Alerts",
        body,
        active="active",
    )


# ---------------------------------------------------------
# JSON API (AUTO REFRESH SOURCE)
# ---------------------------------------------------------

@router.get("/api/active")
def api_active():

    alerts = list_active_alerts(
        window_seconds=3600
    )

    return JSONResponse(alerts)
