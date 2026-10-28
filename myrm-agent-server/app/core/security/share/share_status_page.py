"""Share link status page: browser-friendly 404 responses for public shares.

[INPUT]
- starlette.requests::Request (POS: Accept negotiation)
- app.core.security.share.share_locale (POS: visitor language)

[OUTPUT]
- ShareLinkState: why a share link cannot be served
- render_share_status_html: self-contained HTML status page in the visitor's language
- wants_html: detect browser clients from the Accept header
- share_not_found: browser-friendly HTML 404 or API JSON 404

[POS]
Server business layer. Shared links are time-limited and revocable, so every
public share surface must answer expired/revoked/unavailable links with a
friendly HTML page for browser visitors instead of a raw JSON error, while
keeping the JSON 404 contract for API clients. The page is self-contained
(inline styles + dark mode), written in the visitor's language (English or
Chinese), carries noindex privacy meta, and never exposes internal details
such as token format or storage internals. The wording of every state lives in
one catalog here so the chat and artifact share routes cannot drift apart.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from fastapi import HTTPException, Request
from fastapi.responses import HTMLResponse, Response

from app.core.security.share.share_locale import HTML_LANG, SHARE_BRAND, ShareLang, resolve_share_lang

_STATUS_ICON_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="36" height="36" '
    'viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
    'stroke-linecap="round" stroke-linejoin="round" style="color:#6366f1">'
    '<circle cx="12" cy="12" r="10"/>'
    '<line x1="4.93" y1="4.93" x2="19.07" y2="19.07"/></svg>'
)

_TEMPLATE = """\
<!DOCTYPE html>
<html lang="%(html_lang)s">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<meta name="robots" content="noindex, nofollow"/>
<title>%(title)s</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
display:flex;align-items:center;justify-content:center;min-height:100vh;
background:#f8f9fa;color:#1a1a2e;padding:1rem}
@media(prefers-color-scheme:dark){body{background:#0f0f23;color:#e2e8f0}}
.card{background:#fff;border-radius:12px;padding:2.5rem;max-width:400px;width:100%%;
box-shadow:0 4px 24px rgba(0,0,0,.08);text-align:center}
@media(prefers-color-scheme:dark){.card{background:#1e1e3a;box-shadow:0 4px 24px rgba(0,0,0,.4)}}
.icon{margin-bottom:1rem;display:flex;justify-content:center}
h1{font-size:1.125rem;font-weight:600;margin-bottom:.5rem}
p{font-size:.875rem;color:#666;line-height:1.5;margin-bottom:1.25rem}
@media(prefers-color-scheme:dark){p{color:#94a3b8}}
.brand{font-size:.75rem;color:#9ca3af;margin-bottom:0}
</style>
</head>
<body>
<div class="card">
<div class="icon">%(icon)s</div>
<h1>%(title)s</h1>
<p>%(message)s</p>
<p class="brand">%(brand)s</p>
</div>
</body>
</html>"""


class ShareLinkState(Enum):
    """Why a public share link cannot be served."""

    REVOKED = "revoked"
    EXPIRED = "expired"
    CONTENT_UNAVAILABLE = "content_unavailable"
    FILE_UNAVAILABLE = "file_unavailable"
    CONVERSATION_UNAVAILABLE = "conversation_unavailable"


@dataclass(frozen=True, slots=True)
class _StateCopy:
    title: str
    message: str


_STATE_COPY: dict[ShareLinkState, dict[ShareLang, _StateCopy]] = {
    ShareLinkState.REVOKED: {
        "en": _StateCopy("Link Revoked", "This share link has been revoked by its owner."),
        "zh": _StateCopy("链接已撤销", "分享者已撤销此链接。"),
    },
    ShareLinkState.EXPIRED: {
        "en": _StateCopy("Link Expired", "This share link has expired or is no longer valid."),
        "zh": _StateCopy("链接已过期", "此分享链接已过期或已失效。"),
    },
    ShareLinkState.CONTENT_UNAVAILABLE: {
        "en": _StateCopy("Content Unavailable", "The shared content is no longer available."),
        "zh": _StateCopy("内容不可用", "所分享的内容已不可用。"),
    },
    ShareLinkState.FILE_UNAVAILABLE: {
        "en": _StateCopy("Content Unavailable", "The shared file is no longer available."),
        "zh": _StateCopy("内容不可用", "所分享的文件已不可用。"),
    },
    ShareLinkState.CONVERSATION_UNAVAILABLE: {
        "en": _StateCopy("Content Unavailable", "The shared conversation is no longer available."),
        "zh": _StateCopy("内容不可用", "所分享的对话已不可用。"),
    },
}


def render_share_status_html(state: ShareLinkState, lang: ShareLang = "en") -> str:
    """Return a self-contained HTML page for an unavailable share link."""
    copy = _STATE_COPY[state][lang]
    return _TEMPLATE % {
        "html_lang": HTML_LANG[lang],
        "icon": _STATUS_ICON_SVG,
        "title": copy.title,
        "message": copy.message,
        "brand": SHARE_BRAND[lang],
    }


def wants_html(request: Request) -> bool:
    """Whether the request prefers HTML over JSON (browser navigation)."""
    return "text/html" in request.headers.get("accept", "").lower()


def share_not_found(
    request: Request,
    *,
    detail: str,
    state: ShareLinkState,
    headers: dict[str, str],
) -> Response:
    """Answer a 404 for an unavailable share link.

    Browser visitors get a friendly HTML status page in their language; API
    clients keep the English JSON 404 contract (``detail``).
    """
    if wants_html(request):
        return HTMLResponse(
            content=render_share_status_html(state, resolve_share_lang(request)),
            status_code=404,
            headers=headers,
        )
    raise HTTPException(status_code=404, detail=detail)
