"""The page an OAuth provider sends the user back to once authorization has ended.

[INPUT]
- OAuthOutcome: how the authorization ended
- str | None: the provider's own explanation, which arrives in the query string and so is untrusted

[OUTPUT]
- OAuthOutcome: the five ways a callback can end
- oauth_result_response: one self-contained HTML page for an outcome, in English and Chinese, light and dark

[POS]
The one place the MCP and Google Workspace OAuth callbacks write their HTML. Text that came from the request is escaped
here, so a callback cannot forget to. The copy tells the user what to do next and names no mechanism: status codes,
token fields and exception text stay in the log.
"""

from __future__ import annotations

import html
from dataclasses import dataclass
from enum import Enum

from fastapi.responses import HTMLResponse


class OAuthOutcome(Enum):
    SUCCESS = "success"
    DENIED = "denied"
    EXPIRED = "expired"
    FAILED = "failed"
    UNREACHABLE = "unreachable"


@dataclass(frozen=True)
class _Page:
    status_code: int
    tone: str
    glyph: str
    title: tuple[str, str]
    body: tuple[str, str]


_CIRCLE = '<circle cx="12" cy="12" r="10"/>'
_CHECK = _CIRCLE + '<path d="M8 12.5l3 3 5-6"/>'
_CLOCK = _CIRCLE + '<path d="M12 7v5l3 2"/>'
_CROSS = _CIRCLE + '<path d="M15 9l-6 6M9 9l6 6"/>'

_PAGES: dict[OAuthOutcome, _Page] = {
    OAuthOutcome.SUCCESS: _Page(
        200,
        "ok",
        _CHECK,
        ("Authorization complete", "授权已完成"),
        ("You can close this tab and return to the app.", "可以关闭此页面，回到应用继续使用。"),
    ),
    OAuthOutcome.DENIED: _Page(
        400,
        "bad",
        _CROSS,
        ("Authorization was not completed", "授权未完成"),
        ("Close this tab and try again from the app.", "请关闭此页面，回到应用重新授权。"),
    ),
    OAuthOutcome.EXPIRED: _Page(
        400,
        "warn",
        _CLOCK,
        ("This authorization has expired", "授权已失效"),
        ("Close this tab and start again from the app.", "请关闭此页面，回到应用重新发起授权。"),
    ),
    OAuthOutcome.FAILED: _Page(
        400,
        "bad",
        _CROSS,
        ("Couldn't finish connecting", "未能完成连接"),
        ("Close this tab and try again from the app.", "请关闭此页面，回到应用重试。"),
    ),
    OAuthOutcome.UNREACHABLE: _Page(
        500,
        "bad",
        _CROSS,
        ("Couldn't reach the service", "无法连接到服务"),
        ("Check your network, then close this tab and try again from the app.", "请检查网络，然后关闭此页面，回到应用重试。"),
    ),
}

_STYLE = """\
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;display:flex;align-items:center;justify-content:center;min-height:100vh;background:#f8f9fa;color:#1a1a2e;padding:1rem}
@media(prefers-color-scheme:dark){body{background:#0f0f23;color:#e2e8f0}}
.card{background:#fff;border-radius:12px;padding:2.5rem;max-width:420px;width:100%;box-shadow:0 4px 24px rgba(0,0,0,.08);text-align:center}
@media(prefers-color-scheme:dark){.card{background:#1e1e3a;box-shadow:0 4px 24px rgba(0,0,0,.4)}}
.icon{display:block;margin:0 auto 1rem}
.ok{color:#047857}
.warn{color:#b45309}
.bad{color:#b91c1c}
@media(prefers-color-scheme:dark){.ok{color:#34d399}.warn{color:#fbbf24}.bad{color:#f87171}}
h1{font-size:1.125rem;font-weight:600;margin-bottom:.75rem}
h1 span+span{font-size:.95rem;font-weight:500;margin-top:.15rem}
p{font-size:.9rem;line-height:1.5;color:#475569}
@media(prefers-color-scheme:dark){p{color:#94a3b8}}
span{display:block}
.detail{margin-top:1rem;padding-top:1rem;border-top:1px solid #cbd5e1;font-size:.8rem;overflow-wrap:anywhere}
@media(prefers-color-scheme:dark){.detail{border-top-color:#3a3a5c}}
"""

# Closes the tab the app opened for the redirect; a tab the user opened themselves ignores it and keeps the instruction.
_CLOSE_SCRIPT = "<script>setTimeout(function(){window.close()},3000)</script>"


def _pair(texts: tuple[str, str]) -> str:
    english, chinese = texts
    return f'<span>{english}</span><span lang="zh-Hans">{chinese}</span>'


def oauth_result_response(outcome: OAuthOutcome, *, detail: str | None = None) -> HTMLResponse:
    """The result page for *outcome*; *detail* is the provider's own words, shown escaped under the instruction."""
    page = _PAGES[outcome]
    explanation = f'<p class="detail">{html.escape(detail)}</p>' if detail else ""
    close = _CLOSE_SCRIPT if outcome is OAuthOutcome.SUCCESS else ""
    document = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<meta name="robots" content="noindex, nofollow"/>
<title>{page.title[0]} · {page.title[1]}</title>
<style>
{_STYLE}</style>
</head>
<body>
<main class="card">
<svg class="icon {page.tone}" width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{page.glyph}</svg>
<h1>{_pair(page.title)}</h1>
<p>{_pair(page.body)}</p>
{explanation}
</main>
{close}
</body>
</html>
"""
    return HTMLResponse(content=document, status_code=page.status_code)
