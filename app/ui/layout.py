from typing import Optional


def nav(active):

    def cls(name):
        return "active" if active == name else ""

    return f"""
<nav>
<a class="{cls("dashboard")}" href="/ui/dashboard">Dashboard</a>
<a class="{cls("active")}" href="/ui/active">Active</a>
<a class="{cls("alerts")}" href="/ui/alerts">Alerts</a>
<a href="/ui/sessions">Sessions</a>
</nav>
"""


def page_html(
    title: str,
    body: str,
    active: Optional[str] = None,
):

    return f"""
<html>
<head>
<title>{title}</title>

<style>

body {{
    font-family: Arial;
    background: #0b0f14;
    color: #eee;
    margin: 0;
}}

nav {{
    background: #111;
    padding: 10px;
}}

nav a {{
    color: #bbb;
    margin-right: 20px;
    text-decoration: none;
}}

nav a.active {{
    color: #fff;
    font-weight: bold;
}}

.card {{
    background: #171c24;
    padding: 15px;
    margin: 20px;
    border-radius: 6px;
}}

table {{
    width: 100%;
    border-collapse: collapse;
}}

td, th {{
    padding: 8px;
    border-bottom: 1px solid #333;
}}

#toast {{
    position: fixed;
    bottom: 20px;
    right: 20px;
    background: #222;
    padding: 12px;
    border-radius: 6px;
    display: none;
}}

</style>
</head>

<body>

{nav(active)}

<div>
{body}
</div>

<div id="toast"></div>

<script>

function toast(msg) {{
    const t = document.getElementById("toast");
    t.innerText = msg;
    t.style.display = "block";
    setTimeout(function() {{
        t.style.display = "none";
    }}, 3000);
}}

</script>

</body>
</html>
"""
