"""Single-tenant auth middleware for local, sandbox, and WebUI remote modes.

Local/Tauri: loopback requests receive a fixed local user identity.
Sandbox: trust CP reverse-proxy identity (X-User-Id) on private networks, or
           SANDBOX_API_KEY for direct / remote access.
WebUI Remote: non-loopback requests require SANDBOX_API_KEY.
"""

from __future__ import annotations

import logging

from fastapi import Request, Response, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from app.core.security.auth.identity import (
    LOCAL_USER_ID,
    SANDBOX_FALLBACK_USER_ID,
    is_loopback_ip,
    is_private_network_ip,
    resolve_identity,
)
from app.core.security.auth.public_paths import is_public_path
from app.middleware.auth_audit import AuthEventType, log_auth_event

logger = logging.getLogger(__name__)


def get_local_admin_user_id() -> str:
    """Fixed identity for local single-user runtime."""
    return LOCAL_USER_ID


def is_loopback_client(request: Request) -> bool:
    client_ip = request.client.host if request.client else ""
    return is_loopback_ip(client_ip)


def is_private_network_client(request: Request) -> bool:
    client_ip = request.client.host if request.client else ""
    return is_private_network_ip(client_ip)


def _unauthorized_response(message: str = "Authentication required") -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_401_UNAUTHORIZED,
        content={"detail": message},
    )


class AuthMiddleware(BaseHTTPMiddleware):
    """Inject request.state.user_id for downstream HTTP handlers."""

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        if request.method == "OPTIONS":
            return await call_next(request)

        path = request.url.path
        if is_public_path(path):
            return await call_next(request)

        client_ip = request.client.host if request.client else ""
        identity = resolve_identity(
            path=path,
            method=request.method,
            headers=request.headers,
            client_ip=client_ip,
        )

        if identity.user_id:
            request.state.user_id = identity.user_id
            if not identity.loopback and identity.auth_source in ("sandbox_api_key", "cp_proxy"):
                log_auth_event(
                    AuthEventType.AUTH_SUCCESS,
                    identity.client_ip,
                    auth_source=identity.auth_source,
                    metadata={"path": path},
                )
            return await call_next(request)

        if not identity.loopback:
            log_auth_event(
                AuthEventType.AUTH_FAILURE,
                identity.client_ip,
                metadata={"path": path},
            )
        return _unauthorized_response()


__all__ = [
    "AuthMiddleware",
    "LOCAL_USER_ID",
    "SANDBOX_FALLBACK_USER_ID",
    "get_local_admin_user_id",
    "is_loopback_client",
    "is_private_network_client",
]
