from typing import Optional

def page_html(title: str, body: str, active: Optional[str] = None) -> str:

    def nav_link(name: str, href: str, key: str):
        cls = "active" if active == key else ""
        return f'<a class="{cls}" href="{href}">{name}</a>'

    return f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>{title}</title>
<style>
body {{
    font-family: Arial, sans-serif;
    margin: 0;
    background: #0f172a;
    color: #e2e8f0;
}}

nav {{
    background: #1e293b;
    padding: 14px;
}}

nav a {{
    color: #94a3b8;
    margin-right: 18px;
    text-decoration: none;
    font-weight: 600;
}}

nav a.active {{
    color: white;
}}

.card {{
    background: #1e293b;
    padding: 16px;
    margin: 16px;
    border-radius: 8px;
}}

table {{
    width: 100%;
    border-collapse: collapse;
}}

th, td {{
    padding: 8px;
    border-bottom: 1px solid #334155;
}}

th {{
    text-align: left;
}}

pre {{
    background: #0f172a;
    padding: 8px;
    border-radius: 6px;
    overflow-x: auto;
}}

button {{
    padding: 8px 12px;
    border-radius: 6px;
    border: none;
    background: #3b82f6;
    color: white;
    cursor: pointer;
}}

button:hover {{
    background: #2563eb;
}}

.CRITICAL {{ color: #ff2b2b; font-weight: bold; }}
.HIGH {{ color: #ff8800; }}
.ELEVATED {{ color: #ffaa00; }}
.LOW {{ color: #22c55e; }}
.NONE {{ color: #94a3b8; }}

small {{
    color: #94a3b8;
}}

</style>
</head>
<body>

<nav>
{nav_link("Home", "/", "home")}
{nav_link("Sessions", "/ui/sessions", "sessions")}
{nav_link("Alerts", "/ui/alerts", "alerts")}
{nav_link("Dashboard", "/ui/dashboard", "dashboard")}
{nav_link("Active", "/ui/active", "active")}
</nav>

{body}

</body>
</html>
"""
