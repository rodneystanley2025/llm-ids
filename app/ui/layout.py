from __future__ import annotations

from typing import Optional


# ---------------------------------------------------------
# HTML escape helper
# ---------------------------------------------------------
def _esc(s: str) -> str:
    return (
        (s or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


# ---------------------------------------------------------
# Navigation Bar
# ---------------------------------------------------------
def nav_html(active: Optional[str] = None) -> str:
    """
    active keys:

    home
    sessions
    dashboard
    active
    alerts
    """

    active = (active or "").lower().strip()

    def link(href: str, label: str, key: str) -> str:
        cls = "navlink active" if active == key else "navlink"
        return f"<a class='{cls}' href='{_esc(href)}'>{_esc(label)}</a>"

    # IMPORTANT:
    # These MUST point to UI pages — NOT API endpoints.
    # API endpoints cause the "black JSON screen".
    return f"""
<div class="nav">
  {link("/", "Home", "home")}
  <span class="dot">•</span>

  {link("/ui/sessions", "Sessions", "sessions")}
  <span class="dot">•</span>

  {link("/ui/dashboard", "Dashboard", "dashboard")}
  <span class="dot">•</span>

  {link("/ui/active", "Active", "active")}
  <span class="dot">•</span>

  {link("/ui/alerts", "Alerts", "alerts")}
</div>
"""


# ---------------------------------------------------------
# Shared Page Wrapper
# ---------------------------------------------------------
def page_html(
    title: str,
    body_html: str,
    *,
    active: Optional[str] = None,
    extra_head: str = "",
    extra_css: str = "",
) -> str:
    """
    Wrap page content with shared layout + navbar.

    Every UI page should call this.
    """

    return f"""<!doctype html>
<html>
<head>

<meta charset="utf-8" />
<title>{_esc(title)}</title>

<style>

body {{
  font-family: system-ui, sans-serif;
  max-width: 1100px;
  margin: 24px auto;
  padding: 0 16px;
}}

a {{
  color:#2563eb;
  text-decoration:none;
}}

code {{
  background:#f3f4f6;
  padding:2px 6px;
  border-radius:8px;
}}

.nav {{
  margin-bottom:18px;
}}

.nav .dot {{
  margin:0 6px;
  color:#94a3b8;
}}

.navlink {{
  padding:5px 10px;
  border-radius:10px;
}}

.navlink:hover {{
  background:#f1f5f9;
}}

.navlink.active {{
  background:#0ea5e9;
  color:white;
}}

.card {{
  border:1px solid #e5e7eb;
  border-radius:12px;
  padding:14px;
  margin:12px 0;
}}

.muted {{
  color:#64748b;
  font-size:12px;
}}

table {{
  width:100%;
  border-collapse:collapse;
}}

th, td {{
  padding:10px;
  border-bottom:1px solid #e5e7eb;
  vertical-align:top;
}}

th {{
  text-align:left;
  font-size:12px;
  color:#475569;
  text-transform:uppercase;
}}

.links a {{
  margin-right:10px;
}}

.session-id {{
  max-width:320px;
  overflow:hidden;
  text-overflow:ellipsis;
  white-space:nowrap;
}}

{extra_css}

</style>

{extra_head}

</head>

<body>

{nav_html(active=active)}

{body_html}

</body>
</html>
"""
