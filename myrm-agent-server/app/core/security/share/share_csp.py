"""Content-Security-Policy of a served artifact share page.

[INPUT]
- (none)

[OUTPUT]
- SHARE_CDN_SOURCES: the CDN origins a shared page may load scripts, styles and fonts from
- ARTIFACT_SHARE_CSP: the policy header value of a served HTML share page
- MARKDOWN_SHARE_CSP: the policy header value of a rendered Markdown share page, which runs no script at all

[POS]
Server business layer. A shared artifact has to render the way it did in the in-app preview, and the preview lets a
widget load its libraries from a fixed CDN list (``CDN_ALLOWLIST`` in the frontend's ``widget-theme-bridge.ts``, the
list the widget prompt names). The same list is allowed here for scripts, styles and fonts. Images stay own-origin
and connections stay closed (``img-src`` without remote hosts, ``connect-src 'none'``), so a shared page can load a
charting library but cannot fetch data or pull remote images. ``tests/architecture/test_share_csp_parity.py`` keeps
this list equal to the preview's and a superset of the prompt's. A rendered Markdown page needs no script: it names no
``script-src``, which falls back to ``default-src 'none'`` and refuses inline script too, so even markup the renderer let
through could not run on the application's origin.
"""

from __future__ import annotations

SHARE_CDN_SOURCES: tuple[str, ...] = (
    "https://cdnjs.cloudflare.com",
    "https://cdn.jsdelivr.net",
    "https://unpkg.com",
    "https://esm.sh",
    "https://fonts.googleapis.com",
    "https://fonts.gstatic.com",
)

_CDN = " ".join(SHARE_CDN_SOURCES)

ARTIFACT_SHARE_CSP = (
    "default-src 'none'; "
    f"script-src 'self' 'unsafe-inline' {_CDN}; "
    f"style-src 'self' 'unsafe-inline' {_CDN}; "
    "img-src 'self' data: blob:; "
    f"font-src 'self' data: {_CDN}; "
    "media-src 'self' data: blob:; "
    "connect-src 'none'; "
    "frame-src 'none'; "
    "object-src 'none'"
)

MARKDOWN_SHARE_CSP = "default-src 'none'; style-src 'unsafe-inline'; img-src 'self' data:; frame-src 'none'; object-src 'none'"
