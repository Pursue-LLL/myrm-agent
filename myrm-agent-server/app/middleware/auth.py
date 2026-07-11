"""Single-tenant auth middleware for local, sandbox, and WebUI remote modes.

Local/Tauri: loopback requests receive a fixed local user identity.
Sandbox: trust CP reverse-proxy identity (X-User-Id) on private networks, or
           SANDBOX_API_KEY for direct / remote access.
WebUI Remote: non-loopback requests require SANDBOX_API_KEY or pair token / session.
"""

from __future__ import annotations

import logging

from fastapi import Request, Response, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from app.core.infra.ingress import get_public_ingress_base_url
from app.core.security.auth.identity import (
    LOCAL_USER_ID,
    SANDBOX_FALLBACK_USER_ID,
    is_loopback_ip,
    is_private_network_ip,
    resolve_identity,
)
from app.core.security.auth.public_paths import is_public_path
from app.middleware.auth_audit import AuthEventType, log_auth_event
from app.remote_access.trust_zone import (
    admission_path_to_trust_zone,
    is_local_trusted_admission,
    resolve_admission_path,
)

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
        host_header = request.headers.get("host", "")
        from app.config.deploy_mode import is_local_mode, is_sandbox, is_webui_remote_mode

        if is_local_mode() and is_loopback_client(request):
            public_ingress_base_url = ""
        else:
            public_ingress_base_url = await get_public_ingress_base_url()

        resolved_admission = resolve_admission_path(
            path=path,
            client_ip=client_ip,
            host_header=host_header,
            headers=request.headers,
            public_ingress_base_url=public_ingress_base_url,
            is_sandbox=is_sandbox(),
            is_webui_remote_mode=is_webui_remote_mode(),
        )
        identity = resolve_identity(
            path=path,
            method=request.method,
            headers=request.headers,
            client_ip=client_ip,
            admission_path=resolved_admission.value,
            trust_zone=admission_path_to_trust_zone(resolved_admission).value,
            local_trusted=is_local_trusted_admission(resolved_admission),
            query_string=request.url.query,
            pair_token_override=getattr(request.state, "e2ee_pair_token", None),
        )

        if identity.user_id:
            request.state.user_id = identity.user_id
            request.state.admission_path = identity.admission_path
            request.state.trust_zone = identity.trust_zone
            request.state.local_trusted = identity.local_trusted
            if identity.auth_source:
                request.state.auth_source = identity.auth_source
            if identity.pair_bound_chat_id:
                request.state.pair_bound_chat_id = identity.pair_bound_chat_id
            if identity.session_username:
                request.state.session_username = identity.session_username
            if not identity.loopback and identity.auth_source in ("sandbox_api_key", "cp_proxy"):
                log_auth_event(
                    AuthEventType.AUTH_SUCCESS,
                    identity.client_ip,
                    auth_source=identity.auth_source,
                    metadata={"path": path},
                )
            return await call_next(request)

        if not identity.local_trusted:
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
