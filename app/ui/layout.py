from __future__ import annotations

from typing import Optional


# ---------------------------------------------------------
# MAIN PAGE WRAPPER
# ---------------------------------------------------------

def page_html(
    title: str,
    body: str,
    active: Optional[str] = None,
    request=None,
) -> str:

    # ---------------------------------------------
    # Flash / Toast Message Support
    # ---------------------------------------------
    toast_html = ""

    if request is not None:
        try:
            msg = request.query_params.get("msg")
            if msg:
                toast_html = f"""
                <div id="toast">
                    {msg}
                </div>
                <script>
                setTimeout(() => {{
                    const t=document.getElementById("toast");
                    if(t) t.style.opacity="0";
                }},3000);
                </script>
                """
        except Exception:
            pass

    # ---------------------------------------------
    # Active Nav Helper
    # ---------------------------------------------
    def nav(name: str) -> str:
        return "active" if active == name else ""

    # ---------------------------------------------
    # PAGE HTML
    # ---------------------------------------------
    return f"""
<!DOCTYPE html>
<html>
<head>

<meta charset="utf-8">

<title>{title}</title>

<style>

body {{
    margin:0;
    font-family:system-ui,-apple-system,Segoe UI,Roboto,Arial;
    background:#0e1117;
    color:#e6edf3;
}}

.navbar {{
    background:#161b22;
    padding:14px 20px;
    border-bottom:1px solid #30363d;
}}

.navbar a {{
    color:#8b949e;
    text-decoration:none;
    margin-right:18px;
    font-weight:500;
}}

.navbar a.active {{
    color:#58a6ff;
}}

.container {{
    padding:22px;
}}

.card {{
    background:#161b22;
    border:1px solid #30363d;
    padding:18px;
    margin-bottom:16px;
    border-radius:8px;
}}

table {{
    width:100%;
    border-collapse:collapse;
}}

th,td {{
    border-bottom:1px solid #30363d;
    padding:10px;
    text-align:left;
}}

th {{
    color:#8b949e;
}}

pre {{
    white-space:pre-wrap;
}}

button {{
    background:#238636;
    border:none;
    padding:10px 14px;
    color:white;
    border-radius:6px;
    cursor:pointer;
}}

button:hover {{
    background:#2ea043;
}}

textarea,input {{
    background:#0d1117;
    color:#e6edf3;
    border:1px solid #30363d;
    border-radius:6px;
}}

code {{
    background:#0d1117;
    padding:3px 6px;
    border-radius:6px;
}}

h2 {{
    margin-top:0;
}}

#toast {{
    position:fixed;
    right:20px;
    top:20px;
    background:#238636;
    padding:14px 18px;
    border-radius:8px;
    color:white;
    box-shadow:0 6px 20px rgba(0,0,0,.4);
    z-index:9999;
    transition:opacity .4s ease;
}}

</style>

</head>

<body>

<div class="navbar">

<a class="{nav('dashboard')}" href="/ui/dashboard">Dashboard</a>

<a class="{nav('sessions')}" href="/ui/sessions">Sessions</a>

<a class="{nav('active')}" href="/ui/active">Active</a>

<a class="{nav('alerts')}" href="/ui/alerts">Alerts</a>

<a class="{nav('home')}" href="/">Home</a>

</div>

<div class="container">

{toast_html}

{body}

</div>

</body>

</html>
"""
