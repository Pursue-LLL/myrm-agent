"""Tests for MCP endpoint authentication middleware.

Validates token auth flow: missing header -> 401, invalid token -> 403,
valid token -> pass-through + mark_ready side-effect.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from app.api.mcp import _MCPTokenAuthMiddleware


def _echo_handler(request: Request) -> JSONResponse:
    """Simple echo endpoint to verify middleware pass-through."""
    state = request.scope.get("state", {})
    profile_id = state.get("mcp_profile_id")
    return JSONResponse({"profile_id": profile_id})


def _build_test_client(mock_service=None) -> TestClient:
    """Build a TestClient wrapping the auth middleware around echo handler."""
    inner_app = Starlette(routes=[Route("/mcp", _echo_handler, methods=["GET", "POST"])])
    middleware = _MCPTokenAuthMiddleware(inner_app)

    if mock_service:
        patcher = patch(
            "app.api.mcp.endpoint.get_connect_service",
            return_value=mock_service,
        )
        patcher.start()

    return TestClient(middleware, raise_server_exceptions=False)


class TestMCPTokenAuth:
    """Test _MCPTokenAuthMiddleware behavior."""

    def test_missing_auth_header_returns_401(self):
        tc = _build_test_client()
        response = tc.get("/mcp")
        assert response.status_code == 401
        assert "Authorization" in response.json()["error"]

    def test_non_bearer_auth_returns_401(self):
        tc = _build_test_client()
        response = tc.get("/mcp", headers={"Authorization": "Basic abc123"})
        assert response.status_code == 401

    @patch("app.api.mcp.endpoint._memory_manager_for_agent", new_callable=MagicMock)
    @patch("app.services.connect.get_connect_service")
    def test_invalid_token_returns_403(self, mock_get_service, _mock_manager):
        mock_service = MagicMock()
        mock_service.resolve_token.return_value = None
        mock_get_service.return_value = mock_service

        inner_app = Starlette(routes=[Route("/mcp", _echo_handler, methods=["GET"])])
        middleware = _MCPTokenAuthMiddleware(inner_app)
        tc = TestClient(middleware, raise_server_exceptions=False)
        response = tc.get("/mcp", headers={"Authorization": "Bearer invalid_token"})
        assert response.status_code == 403
        assert "Invalid" in response.json()["error"]

    @patch("app.api.mcp.endpoint._memory_manager_for_agent", new_callable=AsyncMock)
    @patch("app.services.connect.get_connect_service")
    def test_valid_token_passes_through(self, mock_get_service, mock_manager_for_agent):
        from app.services.connect.service import VerifiedConnectToken

        mock_manager_for_agent.return_value = MagicMock()
        mock_service = MagicMock()
        mock_service.resolve_token.return_value = VerifiedConnectToken(
            profile_id="cursor",
            agent_id="default",
        )
        mock_get_service.return_value = mock_service

        inner_app = Starlette(routes=[Route("/mcp", _echo_handler, methods=["GET"])])
        middleware = _MCPTokenAuthMiddleware(inner_app)
        tc = TestClient(middleware, raise_server_exceptions=False)
        response = tc.get("/mcp", headers={"Authorization": "Bearer valid_token"})
        assert response.status_code == 200
        assert response.json()["profile_id"] == "cursor"

    @patch("app.api.mcp.endpoint._memory_manager_for_agent")
    @patch("app.services.connect.get_connect_service")
    def test_valid_token_calls_mark_ready(self, mock_get_service, mock_manager_for_agent):
        from app.services.connect.service import VerifiedConnectToken

        mock_manager_for_agent.return_value = MagicMock()
        mock_service = MagicMock()
        mock_service.resolve_token.return_value = VerifiedConnectToken(
            profile_id="cursor",
            agent_id="default",
        )
        mock_get_service.return_value = mock_service

        inner_app = Starlette(routes=[Route("/mcp", _echo_handler, methods=["GET"])])
        middleware = _MCPTokenAuthMiddleware(inner_app)
        tc = TestClient(middleware, raise_server_exceptions=False)
        tc.get("/mcp", headers={"Authorization": "Bearer valid_token"})
        mock_service.mark_ready.assert_called_once_with("cursor")

    @pytest.mark.asyncio
    async def test_non_http_scope_passes_through(self):
        """Websocket/lifespan scopes should pass through without auth."""
        from unittest.mock import AsyncMock

        inner = AsyncMock()
        middleware = _MCPTokenAuthMiddleware(inner)

        scope = {"type": "websocket"}
        receive = AsyncMock()
        send = AsyncMock()

        await middleware(scope, receive, send)
        inner.assert_called_once_with(scope, receive, send)

    def test_onion_pipeline_origin_guard_rejects_before_token_auth(self):
        """Malicious origin must be rejected with 403 by the outer origin guard before token check."""
        from app.api.mcp.origin_guard import _MCPOriginGuardMiddleware, resolve_origin_guard

        inner_app = Starlette(routes=[Route("/mcp", _echo_handler, methods=["GET"])])
        authed_app = _MCPTokenAuthMiddleware(inner_app)
        pipeline = _MCPOriginGuardMiddleware(authed_app, guard=resolve_origin_guard(host="127.0.0.1"))

        tc = TestClient(pipeline, raise_server_exceptions=False)
        # Even without Authorization header (which would yield 401), outer guard drops it with 403
        response = tc.get(
            "/mcp",
            headers={"Origin": "http://evil-attacker.com", "Host": "127.0.0.1:8080"},
        )
        assert response.status_code == 403
        assert "Origin not allowed" in response.json()["error"]

    @patch("app.api.mcp.endpoint._memory_manager_for_agent", new_callable=AsyncMock)
    @patch("app.services.connect.get_connect_service")
    def test_onion_pipeline_allows_loopback_with_valid_token(
        self, mock_get_service, mock_manager_for_agent
    ):
        """Valid loopback origin with valid token passes both layers to reach echo handler."""
        from app.api.mcp.origin_guard import _MCPOriginGuardMiddleware, resolve_origin_guard
        from app.services.connect.service import VerifiedConnectToken

        mock_manager_for_agent.return_value = MagicMock()
        mock_service = MagicMock()
        mock_service.resolve_token.return_value = VerifiedConnectToken(
            profile_id="cursor",
            agent_id="default",
        )
        mock_get_service.return_value = mock_service

        inner_app = Starlette(routes=[Route("/mcp", _echo_handler, methods=["GET"])])
        authed_app = _MCPTokenAuthMiddleware(inner_app)
        pipeline = _MCPOriginGuardMiddleware(authed_app, guard=resolve_origin_guard(host="127.0.0.1"))

        tc = TestClient(pipeline, raise_server_exceptions=False)
        response = tc.get(
            "/mcp",
            headers={
                "Origin": "http://localhost:3000",
                "Host": "localhost:8080",
                "Authorization": "Bearer valid_token",
            },
        )
        assert response.status_code == 200
        assert response.json()["profile_id"] == "cursor"

