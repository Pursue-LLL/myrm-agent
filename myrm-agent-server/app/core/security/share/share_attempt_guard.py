"""Brute-force lockout for the share password gate.

[INPUT]
- app.core.security.auth.failed_attempt_guard (POS: failure counter with lockout window)
- app.core.security.share.share_hmac::token_fingerprint (POS: non-reversible token key)
- app.core.security.share.share_locale (POS: visitor language)
- app.core.security.share.share_password_page (POS: locked-out gate page)

[OUTPUT]
- password_lockout_response: 429 gate page while a client is locked out of a share, else ``None``
- record_password_failure / record_password_success: feed the lockout from the gate result

[POS]
A password-protected share link is a self-contained signed token, so anyone holding it can try passwords at
network speed. Failures are counted per token and client address: five wrong passwords lock that client out of that
share for the rest of a 60-second window, during which even the correct password is refused so the lock never
reveals whether a guess was right. Visitors who already hold an unlock cookie never reach the gate and are not
affected. Behind a reverse proxy every visitor shares the proxy's address, so an attack on one link can briefly lock
other visitors of that same link out of the password form. State is in-process and bounded.
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import HTMLResponse

from app.core.security.auth.failed_attempt_guard import FailedAttemptGuard
from app.core.security.share.share_hmac import token_fingerprint
from app.core.security.share.share_locale import resolve_share_lang
from app.core.security.share.share_password_page import render_password_gate_html

_guard = FailedAttemptGuard()


def _attempt_key(request: Request, token: str) -> str:
    client = request.client.host if request.client else "unknown"
    return f"{token_fingerprint(token)}|{client}"


def password_lockout_response(request: Request, token: str) -> HTMLResponse | None:
    """The locked-out gate page (HTTP 429) when this client may not try *token* yet."""
    retry_after = _guard.retry_after(_attempt_key(request, token))
    if retry_after is None:
        return None
    return HTMLResponse(
        render_password_gate_html(lang=resolve_share_lang(request), retry_after=retry_after),
        status_code=429,
        headers={"Retry-After": str(retry_after)},
    )


def record_password_failure(request: Request, token: str) -> None:
    _guard.record_failure(_attempt_key(request, token))


def record_password_success(request: Request, token: str) -> None:
    _guard.clear(_attempt_key(request, token))
