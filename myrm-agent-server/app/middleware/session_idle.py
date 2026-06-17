"""Refresh WebUI session cookies on activity for remote-exposed admission paths.

[POS]
Sliding idle timeout for remote-exposed WebUI sessions.
"""

from __future__ import annotations

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from app.remote_access.trust_zone import TrustZone
from app.services.webui.session import (
    REMOTE_IDLE_TTL_SECONDS,
    SESSION_COOKIE_NAME,
    SESSION_TTL_SECONDS,
    create_session_value,
)


def _request_uses_https(request: Request) -> bool:
    if request.url.scheme == "https":
        return True
    forwarded = request.headers.get("x-forwarded-proto", "").split(",")[0].strip().lower()
    return forwarded == "https"


class SessionIdleMiddleware(BaseHTTPMiddleware):
    """Slide remote WebUI session expiry on each authenticated request."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        session_username = getattr(request.state, "session_username", None)
        trust_zone = getattr(request.state, "trust_zone", None)
        if not session_username or trust_zone != TrustZone.REMOTE_EXPOSED.value:
            return response

        refreshed = create_session_value(session_username)
        response.set_cookie(
            key=SESSION_COOKIE_NAME,
            value=refreshed,
            max_age=min(SESSION_TTL_SECONDS, REMOTE_IDLE_TTL_SECONDS),
            httponly=True,
            samesite="lax",
            secure=_request_uses_https(request),
            path="/",
        )
        return response


__all__ = ["SessionIdleMiddleware"]
