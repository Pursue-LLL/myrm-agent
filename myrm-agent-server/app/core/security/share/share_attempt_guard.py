"""Brute-force lockout for the share password gate.

[INPUT]
- app.core.security.auth.failed_attempt_guard (POS: failure counter with lockout window)
- app.core.security.share.share_hmac::token_fingerprint (POS: non-reversible token key)
- app.core.security.share.share_locale (POS: visitor language)
- app.core.security.share.share_password_page (POS: locked-out gate page)

[OUTPUT]
- password_lockout_response: 429 gate page while a client is locked out of a share, else ``None``
- record_password_failure / record_password_success: feed the lockout from the gate result (a failure reports
  whether it just engaged the lock)

[POS]
A password-protected share link is a self-contained signed token, so anyone holding it can try passwords at
network speed. Failures are counted per token and client address: five wrong passwords lock that client out of that
share for the rest of a five-minute window (longer than the login lock because the visitors are anonymous and a
legitimate recipient only waits), during which even the correct password is refused so the lock never reveals
whether a guess was right; the locked page reloads itself once the lock lifts. Visitors who already hold an unlock
cookie never reach the gate and are not affected.

The client address is ``request.client.host``. uvicorn rewrites it from X-Forwarded-For only for peers listed in
FORWARDED_ALLOW_IPS (default 127.0.0.1), so behind a proxy on another host or container network every visitor
shares the proxy's address and an attack on one link can briefly lock its other visitors out of the form, unless
FORWARDED_ALLOW_IPS names that proxy (never ``*``: any client could then forge the header and dodge the lock).
State is in-process and bounded, so a multi-process server (SERVER_MODE=granian) counts per process.
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import HTMLResponse

from app.core.security.auth.failed_attempt_guard import FailedAttemptGuard
from app.core.security.share.share_hmac import token_fingerprint
from app.core.security.share.share_locale import resolve_share_lang
from app.core.security.share.share_password_page import render_password_gate_html

_LOCK_WINDOW_SECONDS = 300.0


def _new_guard() -> FailedAttemptGuard:
    return FailedAttemptGuard(window_seconds=_LOCK_WINDOW_SECONDS)


_guard = _new_guard()


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


def record_password_failure(request: Request, token: str) -> bool:
    """Count a wrong password; ``True`` when this failure just locked the client out of *token*."""
    return _guard.record_failure(_attempt_key(request, token))


def record_password_success(request: Request, token: str) -> None:
    _guard.clear(_attempt_key(request, token))
