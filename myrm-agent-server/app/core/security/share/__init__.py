"""Shared-link security primitives (HMAC tokens, privacy headers, unlock cookies).

[INPUT]
- app.config.settings::settings (POS: signing key material)
- starlette.requests::Request / fastapi Response (POS: password-gate & unlock-cookie I/O)

[OUTPUT]
- Aggregate facade re-exporting every public name from the ``share`` subpackage:
  - share_hmac: create/sign/parse/verify stateless share tokens, token_fingerprint
  - share_headers: shared noindex/nofollow + no-store + no-referrer privacy headers
  - share_status_page: browser-friendly share 404 page + Accept-based JSON fallback
  - share_unlock: per-share unlock-cookie name/credential mechanics
  - share_password_page: self-contained password-gate HTML + submission parsing

[POS]
Server business layer. Single shared-link security domain consumed by both the
artifact and chat public share surfaces so security parameters (cookie
attributes, TTL thresholds, privacy headers, password handling) stay centralized
and can never drift apart.
"""

from app.core.security.share.share_headers import SHARE_PRIVACY_HEADERS
from app.core.security.share.share_hmac import (
    b64url_decode,
    b64url_encode,
    create_share_token,
    is_password_protected,
    parse_share_token,
    sign_share_token,
    token_fingerprint,
)
from app.core.security.share.share_password_page import (
    render_password_gate_html,
    resolve_gate_password,
)
from app.core.security.share.share_status_page import (
    render_share_status_html,
    share_not_found,
    wants_html,
)
from app.core.security.share.share_unlock import (
    attach_unlock_cookie,
    build_unlock_credential,
    parse_unlock_credential,
    unlock_cookie_name,
)

__all__ = [
    "SHARE_PRIVACY_HEADERS",
    "attach_unlock_cookie",
    "b64url_decode",
    "b64url_encode",
    "build_unlock_credential",
    "create_share_token",
    "is_password_protected",
    "parse_share_token",
    "parse_unlock_credential",
    "render_password_gate_html",
    "render_share_status_html",
    "resolve_gate_password",
    "share_not_found",
    "sign_share_token",
    "token_fingerprint",
    "unlock_cookie_name",
    "wants_html",
]
