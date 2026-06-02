"""WebSocket handshake authentication middleware (ASGI)."""

from __future__ import annotations

from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.security.auth.identity import resolve_identity_from_ws_scope
from app.core.security.auth.public_paths import is_public_path
from app.middleware.auth_audit import AuthEventType, log_auth_event

_WS_HTTP_FORBIDDEN = 403


class WsAuthMiddleware:
    """Inject scope.state.user_id for WebSocket connections before route handlers run."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "websocket":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if is_public_path(path):
            await self.app(scope, receive, send)
            return

        from app.platform_utils.deployment_capabilities import get_deployment_capabilities

        identity = resolve_identity_from_ws_scope(scope)
        caps = get_deployment_capabilities()

        if identity.user_id:
            state = scope.setdefault("state", {})
            state["user_id"] = identity.user_id
            if not identity.loopback and identity.auth_source in ("sandbox_api_key", "cp_proxy"):
                log_auth_event(
                    AuthEventType.AUTH_SUCCESS,
                    identity.client_ip,
                    auth_source=identity.auth_source,
                    metadata={"path": path, "transport": "websocket"},
                )
            await self.app(scope, receive, send)
            return

        if caps.requires_strict_ws_auth and not identity.loopback:
            log_auth_event(
                AuthEventType.AUTH_FAILURE,
                identity.client_ip,
                metadata={"path": path, "transport": "websocket"},
            )
            await self._reject_websocket(send)
            return

        state = scope.setdefault("state", {})
        state["user_id"] = identity.user_id or "sandbox"
        await self.app(scope, receive, send)

    @staticmethod
    async def _reject_websocket(send: Send) -> None:
        """Reject WebSocket upgrade with HTTP 403 before accept."""
        await send(
            {
                "type": "websocket.http.response.start",
                "status": _WS_HTTP_FORBIDDEN,
                "headers": [(b"content-type", b"text/plain")],
            }
        )
        await send({"type": "websocket.http.response.body", "body": b"Unauthorized"})


__all__ = ["WsAuthMiddleware"]
