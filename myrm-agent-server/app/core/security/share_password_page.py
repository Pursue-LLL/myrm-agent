"""Minimal HTML page for password-gated share links.

[INPUT]
- none

[OUTPUT]
- render_password_gate_html: returns a self-contained HTML page

[POS]
Renders a lightweight, self-contained password prompt page for public share
endpoints. The form submits the password as a query parameter ``p`` to the
same URL, letting the share API verify the token with the supplied password.
"""

from __future__ import annotations

_LOCK_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 24 24" '
    'fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" '
    'stroke-linejoin="round" style="color:#6366f1">'
    '<rect width="18" height="11" x="3" y="11" rx="2" ry="2"/>'
    '<path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>'
)

_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>Password Required</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
display:flex;align-items:center;justify-content:center;min-height:100vh;
background:#f8f9fa;color:#1a1a2e}
@media(prefers-color-scheme:dark){body{background:#0f0f23;color:#e2e8f0}}
.card{background:#fff;border-radius:12px;padding:2rem;max-width:360px;width:90%%;
box-shadow:0 4px 24px rgba(0,0,0,.08);text-align:center}
@media(prefers-color-scheme:dark){.card{background:#1e1e3a;box-shadow:0 4px 24px rgba(0,0,0,.4)}}
.icon{margin-bottom:.75rem;display:flex;justify-content:center}
h1{font-size:1.125rem;font-weight:600;margin-bottom:.25rem}
p{font-size:.875rem;color:#666;margin-bottom:1.25rem}
@media(prefers-color-scheme:dark){p{color:#94a3b8}}
input[type=password]{width:100%%;padding:.625rem .75rem;border:1px solid #ddd;
border-radius:8px;font-size:.875rem;background:#fafafa;outline:none;
transition:border-color .15s}
@media(prefers-color-scheme:dark){input[type=password]{background:#2a2a4a;border-color:#444;color:#e2e8f0}}
input[type=password]:focus{border-color:#6366f1}
button{width:100%%;padding:.625rem;border:none;border-radius:8px;
background:#6366f1;color:#fff;font-size:.875rem;font-weight:500;
cursor:pointer;margin-top:.75rem;transition:background .15s}
button:hover{background:#4f46e5}
.err{color:#ef4444;font-size:.8125rem;margin-top:.5rem;display:%(err_display)s}
</style>
</head>
<body>
<div class="card">
<div class="icon">%(lock_svg)s</div>
<h1>Password Required</h1>
<p>This shared content is password-protected.</p>
<form method="get" action="">
<input type="password" name="p" placeholder="Enter password" required autofocus/>
<button type="submit">Unlock</button>
</form>
<div class="err">%(err_msg)s</div>
</div>
</body>
</html>"""


def render_password_gate_html(*, wrong_password: bool = False) -> str:
    """Return self-contained HTML for the password gate page."""
    return _TEMPLATE % {
        "lock_svg": _LOCK_SVG,
        "err_display": "block" if wrong_password else "none",
        "err_msg": "Incorrect password. Please try again." if wrong_password else "",
    }
