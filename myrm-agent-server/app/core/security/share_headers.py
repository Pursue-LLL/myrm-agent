"""Shared privacy response headers for public share surfaces (chat + artifact).

[INPUT]
- (none)

[OUTPUT]
- SHARE_PRIVACY_HEADERS: consumed by chat and artifact public share endpoints

[POS]
Server business layer. Every served share payload (chat page, artifact bundle
entry, static asset) must carry noindex/nofollow + no-store so shared work
products are never search-engine indexed and revoking a link cannot be bypassed
by browser or CDN caches. ``Referrer-Policy: no-referrer`` stops the share URL
(which embeds a bearer-style HMAC token) from leaking to third-party origins
when a viewer follows an external link on the shared page. HTML-only security
headers (CSP etc.) intentionally stay in each caller because the two share
surfaces enforce different policies.
"""

from __future__ import annotations

SHARE_PRIVACY_HEADERS: dict[str, str] = {
    "X-Robots-Tag": "noindex, nofollow",
    "Cache-Control": "no-store",
    "Referrer-Policy": "no-referrer",
}
