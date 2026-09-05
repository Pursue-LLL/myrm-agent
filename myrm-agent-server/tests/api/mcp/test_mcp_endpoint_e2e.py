"""End-to-end HTTP integration tests for the /mcp endpoint with Origin & DNS-rebinding guard.

[INPUT]
- app.api.mcp.origin_guard::_MCPOriginGuardMiddleware, resolve_origin_guard
- app.api.mcp.endpoint::_MCPTokenAuthMiddleware

[OUTPUT]
- Integration test suite verifying HTTP MCP endpoint mounting, origin filtering, and auth flow

[POS]
E2E integration test for the /mcp HTTP server endpoint and its security middlewares.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.api.mcp.endpoint import _MCPTokenAuthMiddleware
from app.api.mcp.origin_guard import _MCPOriginGuardMiddleware, resolve_origin_guard
from app.services.connect.service import VerifiedConnectToken


@pytest.fixture
def mcp_test_app() -> FastAPI:
    """Build a minimal FastAPI application with /mcp endpoint wired like setup_mcp_endpoint."""
    app = FastAPI()

    async def _mock_mcp_handler(request: Request) -> JSONResponse:
        state = request.scope.get("state", {})
        return JSONResponse({
            "status": "mcp_ok",
            "agent_id": state.get("mcp_agent_id"),
            "profile_id": state.get("mcp_profile_id"),
        })

    # Wire inner handler -> token auth -> origin guard -> mount at /mcp
    authed_app = _MCPTokenAuthMiddleware(_mock_mcp_handler)
    origin_guard = resolve_origin_guard(host="127.0.0.1")
    guarded_app = _MCPOriginGuardMiddleware(authed_app, guard=origin_guard)
    app.mount("/mcp", guarded_app)
    return app


class TestMCPEndpointFullPipelineE2E:
    """Full HTTP pipeline tests against /mcp mounted on FastAPI."""

    def test_e2e_dns_rebinding_attack_blocked_at_gateway(self, mcp_test_app: FastAPI) -> None:
        """Simulate an attacker who rebinds attacker.com to 127.0.0.1 and sends requests."""
        client = TestClient(mcp_test_app, raise_server_exceptions=False)
        response = client.post(
            "/mcp/",
            headers={
                "Host": "attacker.com:8080",
                "Origin": "http://attacker.com",
                "Authorization": "Bearer any_token",
            },
        )
        assert response.status_code == 403
        data = response.json()
        assert "Forbidden" in data["error"]
        assert ("Origin not allowed" in data["error"] or "Host not allowed" in data["error"])

    def test_e2e_cross_site_browser_page_blocked_even_with_leaked_token(
        self,
        mcp_test_app: FastAPI,
    ) -> None:
        """Even if the attacker somehow obtained a valid token, foreign browser Origin is blocked."""
        client = TestClient(mcp_test_app, raise_server_exceptions=False)
        response = client.get(
            "/mcp/",
            headers={
                "Origin": "https://malicious-webpage.com",
                "Host": "127.0.0.1:8080",
                "Authorization": "Bearer myrm_mcp_leaked_token_123",
            },
        )
        assert response.status_code == 403
        assert "Origin not allowed" in response.json()["error"]

    def test_e2e_native_developer_tools_allowed_without_origin(
        self,
        mcp_test_app: FastAPI,
    ) -> None:
        """Cursor, Claude Code, curl, and MCP SDK omit Origin and must pass the guard."""
        client = TestClient(mcp_test_app, raise_server_exceptions=False)
        # Without Origin, it passes OriginGuard and reaches TokenAuth -> missing header gives 401
        response = client.get(
            "/mcp/",
            headers={"Host": "127.0.0.1:8080"},
        )
        assert response.status_code == 401
        assert "Missing or invalid Authorization header" in response.json()["error"]

    @patch("app.api.mcp.endpoint._memory_manager_for_agent", new_callable=AsyncMock)
    @patch("app.services.connect.get_connect_service")
    def test_e2e_legitimate_webui_and_connect_token_passes(
        self,
        mock_get_service: MagicMock,
        mock_manager: MagicMock,
        mcp_test_app: FastAPI,
    ) -> None:
        """Legitimate WebUI connection with valid token traverses entire stack to MCP handler."""
        mock_manager.return_value = MagicMock()
        mock_service = MagicMock()
        mock_service.resolve_token.return_value = VerifiedConnectToken(
            profile_id="cursor",
            agent_id="default",
        )
        mock_get_service.return_value = mock_service

        client = TestClient(mcp_test_app, raise_server_exceptions=False)
        response = client.post(
            "/mcp/",
            headers={
                "Origin": "http://localhost:3000",
                "Host": "127.0.0.1:8080",
                "Authorization": "Bearer myrm_mcp_valid_token_abc",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "mcp_ok"
        assert data["profile_id"] == "cursor"
        assert data["agent_id"] == "default"
        mock_service.mark_ready.assert_called_once_with("cursor")
