from __future__ import annotations

from typing import Optional


def _esc(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def nav_html(active: Optional[str] = None) -> str:
    """
    active: one of {"home","sessions","active","alerts"} to highlight the current page.
    """
    active = (active or "").lower().strip()

    def link(href: str, label: str, key: str) -> str:
        cls = "navlink active" if active == key else "navlink"
        return f"<a class='{cls}' href='{_esc(href)}'>{_esc(label)}</a>"

    return f"""
<div class="nav">
  {link("/", "Home", "home")}
  <span class="dot">•</span>
  {link("/ui/sessions", "Sessions", "sessions")}
  <span class="dot">•</span>
  {link("/v1/active", "Active", "active")}
  <span class="dot">•</span>
  {link("/v1/alerts", "Alerts", "alerts")}
</div>
"""


def page_html(
    title: str,
    body_html: str,
    *,
    active: Optional[str] = None,
    extra_head: str = "",
    extra_css: str = "",
) -> str:
    """
    Wraps a page with shared CSS + nav.
    """
    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title>{_esc(title)}</title>
  <style>
    body {{ font-family: system-ui, sans-serif; max-width: 980px; margin: 24px auto; padding: 0 16px; }}
    a {{ color:#2563eb; text-decoration:none; }}
    code {{ background:#f3f4f6; padding:2px 6px; border-radius:8px; }}

    .nav {{ margin-bottom: 16px; }}
    .nav .dot {{ margin: 0 6px; color:#94a3b8; }}
    .navlink {{ padding: 4px 8px; border-radius: 10px; }}
    .navlink:hover {{ background:#f1f5f9; }}
    .navlink.active {{ background:#0ea5e9; color:white; }}

    .card {{ border:1px solid #e5e7eb; border-radius:12px; padding:14px; margin:12px 0; }}
    .muted {{ color:#64748b; font-size: 12px; }}

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
