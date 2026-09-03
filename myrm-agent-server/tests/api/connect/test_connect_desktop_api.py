"""Integration tests for Connect Desktop API endpoints.

Tests verify:
- POST /connect/generate with expose_desktop=True/False
- GET /connect/status returning expose_desktop
- GET /connect/agent-capabilities/{agent_id} endpoint
"""

from collections.abc import Iterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from tests.support.minimal_app import build_minimal_app

_app = build_minimal_app(preset="connect")
API_PREFIX = "/api/v1"


@pytest.fixture(scope="module")
def client() -> Iterator[TestClient]:
    """Create test client from minimal app with auth bypassed."""
    import app.services.connect.service as svc

    svc._service = None
    with (
        patch(
            "app.core.security.auth.identity.is_loopback_ip",
            return_value=True,
        ),
        patch(
            "app.services.connect.service.is_local_mode",
            return_value=False,
        ),
    ):
        yield TestClient(_app)


class TestConnectGenerateDesktopAPI:
    """Test desktop tools flag in config generation."""

    def test_generate_default_expose_desktop_false(self, client: TestClient) -> None:
        response = client.post(
            f"{API_PREFIX}/connect/generate",
            json={"profile_id": "claude_code"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["expose_desktop"] is False
        assert data["desktop_tools"] == []
        assert "myrm-memory" in data["config_json"]["mcpServers"]
        assert "myrm" not in data["config_json"]["mcpServers"]

    def test_generate_expose_desktop_true(self, client: TestClient) -> None:
        response = client.post(
            f"{API_PREFIX}/connect/generate",
            json={"profile_id": "cursor", "expose_desktop": True},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["expose_desktop"] is True
        assert len(data["desktop_tools"]) == 3
        assert "desktop_snapshot_tool" in data["desktop_tools"]
        assert "desktop_interact_tool" in data["desktop_tools"]
        assert "desktop_vision_tool" in data["desktop_tools"]
        assert "myrm" in data["config_json"]["mcpServers"]
        assert "myrm-memory" not in data["config_json"]["mcpServers"]

    def test_status_endpoint_returns_expose_desktop(self, client: TestClient) -> None:
        client.post(
            f"{API_PREFIX}/connect/generate",
            json={"profile_id": "windsurf", "expose_desktop": True},
        )
        response = client.get(f"{API_PREFIX}/connect/status/windsurf")
        assert response.status_code == 200
        data = response.json()
        assert data["expose_desktop"] is True


class TestAgentCapabilitiesAPI:
    """Test /connect/agent-capabilities/{agent_id} endpoint."""

    def test_agent_capabilities_not_found(self, client: TestClient) -> None:
        with patch(
            "app.services.agent.profile.profile_resolver.get_agent_profile_resolver"
        ) as mock_resolver_fn:
            mock_resolver = MagicMock()
            mock_resolver.resolve = AsyncMock(return_value=None)
            mock_resolver_fn.return_value = mock_resolver

            response = client.get(f"{API_PREFIX}/connect/agent-capabilities/nonexistent_agent")
            assert response.status_code == 404

    def test_agent_capabilities_desktop_supported(self, client: TestClient) -> None:
        mock_profile = MagicMock()
        mock_profile.agent_id = "desk-agent"
        mock_profile.enabled_builtin_tools = ["enable_computer_use"]

        with (
            patch(
                "app.services.agent.profile.profile_resolver.get_agent_profile_resolver"
            ) as mock_resolver_fn,
            patch(
                "app.config.computer_use_deploy.is_computer_use_deploy_supported",
                return_value=True,
            ),
        ):
            mock_resolver = MagicMock()
            mock_resolver.resolve = AsyncMock(return_value=mock_profile)
            mock_resolver_fn.return_value = mock_resolver

            response = client.get(f"{API_PREFIX}/connect/agent-capabilities/desk-agent")
            assert response.status_code == 200
            data = response.json()
            assert data["agent_id"] == "desk-agent"
            assert data["has_computer_use"] is True
            assert data["desktop_supported"] is True
            assert data["can_expose_desktop"] is True

    def test_agent_capabilities_desktop_unsupported(self, client: TestClient) -> None:
        mock_profile = MagicMock()
        mock_profile.agent_id = "plain-agent"
        mock_profile.enabled_builtin_tools = []

        with (
            patch(
                "app.services.agent.profile.profile_resolver.get_agent_profile_resolver"
            ) as mock_resolver_fn,
            patch(
                "app.config.computer_use_deploy.is_computer_use_deploy_supported",
                return_value=True,
            ),
        ):
            mock_resolver = MagicMock()
            mock_resolver.resolve = AsyncMock(return_value=mock_profile)
            mock_resolver_fn.return_value = mock_resolver

            response = client.get(f"{API_PREFIX}/connect/agent-capabilities/plain-agent")
            assert response.status_code == 200
            data = response.json()
            assert data["agent_id"] == "plain-agent"
            assert data["has_computer_use"] is False
            assert data["can_expose_desktop"] is False
