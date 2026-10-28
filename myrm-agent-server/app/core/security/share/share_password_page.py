"""Password gate for public share links: HTML page + submission parsing.

[INPUT]
- starlette.requests::Request (POS: password-gate form submission)
- app.core.security.share.share_locale (POS: visitor language)

[OUTPUT]
- render_password_gate_html: returns a self-contained HTML page in the visitor's language (optionally in the locked-out variant)
- password_gate_response: the 403 gate page for a request, optionally flagging a wrong password
- resolve_gate_password: resolves the gate password from a POST form / GET query

[POS]
Renders a lightweight, self-contained password prompt page for public share
endpoints and resolves the submitted password. The form posts the password as
a body field so it never appears in the URL (CWE-598); the legacy ``p`` query
parameter is still accepted so links shared before the change keep unlocking.
The page is written in the visitor's language (English or Chinese). The
locked-out variant disables the form and reloads itself once the lock has
lifted, so a visitor who waits is never left on a dead page.
"""

from __future__ import annotations

from dataclasses import dataclass

from starlette.requests import Request
from starlette.responses import HTMLResponse

from app.core.security.share.share_locale import ShareLang, resolve_share_lang

_LOCK_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 24 24" '
    'fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" '
    'stroke-linejoin="round" style="color:#6366f1">'
    '<rect width="18" height="11" x="3" y="11" rx="2" ry="2"/>'
    '<path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>'
)

_TEMPLATE = """\
<!DOCTYPE html>
<html lang="%(html_lang)s">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>%(refresh)s
<title>%(title)s</title>
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
button:disabled,input:disabled{opacity:.5;cursor:not-allowed}
button:disabled:hover{background:#6366f1}
.err{color:#ef4444;font-size:.8125rem;margin-top:.5rem;display:%(err_display)s}
@media(prefers-reduced-motion:reduce){*,*::before,*::after{animation-duration:0.01ms !important;animation-iteration-count:1 !important;transition-duration:0.01ms !important}}
</style>
</head>
<body>
<div class="card">
<div class="icon">%(lock_svg)s</div>
<h1>%(title)s</h1>
<p>%(prompt)s</p>
<form method="post" action="">
<input type="password" name="p" placeholder="%(placeholder)s" required autofocus%(disabled)s/>
<button type="submit"%(disabled)s>%(button)s</button>
</form>
<div class="err">%(err_msg)s</div>
</div>
</body>
</html>"""


@dataclass(frozen=True, slots=True)
class _GateCopy:
    html_lang: str
    title: str
    prompt: str
    placeholder: str
    button: str
    wrong_password: str
    locked: str


_GATE_COPY: dict[ShareLang, _GateCopy] = {
    "en": _GateCopy(
        html_lang="en",
        title="Password Required",
        prompt="This shared content is password-protected.",
        placeholder="Enter password",
        button="Unlock",
        wrong_password="Incorrect password. Please try again.",
        locked="Too many incorrect attempts. Try again in {seconds} seconds.",
    ),
    "zh": _GateCopy(
        html_lang="zh-CN",
        title="需要密码",
        prompt="此分享内容受密码保护。",
        placeholder="输入密码",
        button="解锁",
        wrong_password="密码错误，请重试。",
        locked="错误次数过多，请 {seconds} 秒后重试。",
    ),
}


def render_password_gate_html(
    *,
    lang: ShareLang = "en",
    wrong_password: bool = False,
    retry_after: int | None = None,
) -> str:
    """Return self-contained HTML for the password gate page.

    ``retry_after`` renders the locked-out variant: the form is disabled, the
    visitor is told how many seconds remain before another attempt is accepted,
    and the page reloads itself just after that moment (the remaining time is
    truncated to whole seconds, so one extra second lands after the lock lifts).
    """
    copy = _GATE_COPY[lang]
    if retry_after is not None:
        message = copy.locked.format(seconds=retry_after)
    elif wrong_password:
        message = copy.wrong_password
    else:
        message = ""
    return _TEMPLATE % {
        "html_lang": copy.html_lang,
        "refresh": f'<meta http-equiv="refresh" content="{retry_after + 1}"/>' if retry_after is not None else "",
        "title": copy.title,
        "prompt": copy.prompt,
        "placeholder": copy.placeholder,
        "button": copy.button,
        "lock_svg": _LOCK_SVG,
        "err_display": "block" if message else "none",
        "err_msg": message,
        "disabled": " disabled" if retry_after is not None else "",
    }


def password_gate_response(request: Request, *, wrong_password: bool = False) -> HTMLResponse:
    """The 403 password gate page for *request*, in the visitor's language."""
    return HTMLResponse(
        render_password_gate_html(lang=resolve_share_lang(request), wrong_password=wrong_password),
        status_code=403,
    )


async def resolve_gate_password(request: Request) -> str | None:
    """Resolve the password from a password-gate submission.

    POST reads the ``p`` form field so the password never reaches the URL
    (CWE-598). GET also accepts a ``p`` query parameter for links that carry
    the password in the URL. Returns ``None`` when absent.
    """
    if request.method == "POST":
        form = await request.form()
        value = form.get("p")
        return str(value) if value else None
    return request.query_params.get("p")
