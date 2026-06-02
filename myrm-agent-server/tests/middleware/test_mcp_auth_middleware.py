"""Tests for MCP endpoint authentication middleware.

Validates token auth flow: missing header -> 401, invalid token -> 403,
valid token -> pass-through + mark_ready side-effect.
"""

from unittest.mock import MagicMock, patch

import pytest
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from app.api.mcp_endpoint import _MCPTokenAuthMiddleware


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
            "app.api.mcp_endpoint.get_connect_service",
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

    @patch("app.services.connect.get_connect_service")
    def test_invalid_token_returns_403(self, mock_get_service):
        mock_service = MagicMock()
        mock_service.verify_token.return_value = None
        mock_get_service.return_value = mock_service

        inner_app = Starlette(routes=[Route("/mcp", _echo_handler, methods=["GET"])])
        middleware = _MCPTokenAuthMiddleware(inner_app)
        tc = TestClient(middleware, raise_server_exceptions=False)
        response = tc.get("/mcp", headers={"Authorization": "Bearer invalid_token"})
        assert response.status_code == 403
        assert "Invalid" in response.json()["error"]

    @patch("app.services.connect.get_connect_service")
    def test_valid_token_passes_through(self, mock_get_service):
        mock_service = MagicMock()
        mock_service.verify_token.return_value = "cursor"
        mock_get_service.return_value = mock_service

        inner_app = Starlette(routes=[Route("/mcp", _echo_handler, methods=["GET"])])
        middleware = _MCPTokenAuthMiddleware(inner_app)
        tc = TestClient(middleware, raise_server_exceptions=False)
        response = tc.get("/mcp", headers={"Authorization": "Bearer valid_token"})
        assert response.status_code == 200
        assert response.json()["profile_id"] == "cursor"

    @patch("app.services.connect.get_connect_service")
    def test_valid_token_calls_mark_ready(self, mock_get_service):
        mock_service = MagicMock()
        mock_service.verify_token.return_value = "cursor"
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
