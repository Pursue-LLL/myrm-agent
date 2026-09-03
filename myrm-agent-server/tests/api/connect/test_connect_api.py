"""Integration tests for Connect API router.

Tests the full API flow: list profiles, generate config, doctor, revoke,
and status endpoints using FastAPI TestClient.
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
    """Create test client from the real application with auth bypassed."""
    import app.services.connect.service as svc

    svc._service = None
    with (
        patch(
            "app.core.security.auth.identity.is_loopback_ip",
            return_value=True,
        ),
        # Force the token-only doctor path: file verification would otherwise
        # read real user config files and make the API tests environment-bound.
        patch(
            "app.services.connect.service.is_local_mode",
            return_value=False,
        ),
    ):
        yield TestClient(_app)


class TestConnectProfilesAPI:
    """Test GET /connect/profiles endpoint."""

    def test_list_profiles_returns_200(self, client: TestClient):
        response = client.get(f"{API_PREFIX}/connect/profiles")
        assert response.status_code == 200

    def test_list_profiles_has_5_items(self, client: TestClient):
        response = client.get(f"{API_PREFIX}/connect/profiles")
        data = response.json()
        assert len(data) == 5

    def test_profiles_have_required_fields(self, client: TestClient):
        response = client.get(f"{API_PREFIX}/connect/profiles")
        for profile in response.json():
            assert "id" in profile
            assert "label" in profile
            assert "description" in profile
            assert "config_file_path" in profile
            assert "status" in profile

    def test_profiles_default_status_is_missing(self, client: TestClient):
        response = client.get(f"{API_PREFIX}/connect/profiles")
        for profile in response.json():
            assert profile["status"] == "missing"


class TestConnectGenerateAPI:
    """Test POST /connect/generate endpoint."""

    def test_generate_config_returns_200(self, client: TestClient):
        response = client.post(f"{API_PREFIX}/connect/generate", json={"profile_id": "claude_code"})
        assert response.status_code == 200

    def test_generate_returns_token(self, client: TestClient):
        response = client.post(f"{API_PREFIX}/connect/generate", json={"profile_id": "cursor"})
        data = response.json()
        assert data["token"].startswith("myrm_mcp_")
        assert data["mcp_url"].endswith("/mcp")
        assert "mcpServers" in data["config_json"]
        assert data["instructions"]

    def test_generate_unknown_profile_returns_error(self, client: TestClient):
        response = client.post(f"{API_PREFIX}/connect/generate", json={"profile_id": "nonexistent"})
        assert response.status_code in (400, 422, 500)

    def test_generate_codex_returns_toml(self, client: TestClient):
        response = client.post(f"{API_PREFIX}/connect/generate", json={"profile_id": "codex"})
        data = response.json()
        assert data["config_json"]["_format"] == "toml"
        assert "[mcp_servers.myrm-memory]" in data["config_json"]["_toml_snippet"]

    def test_generate_default_expose_desktop_false(self, client: TestClient):
        response = client.post(f"{API_PREFIX}/connect/generate", json={"profile_id": "claude_code"})
        assert response.status_code == 200
        data = response.json()
        assert data["expose_desktop"] is False
        assert data["desktop_tools"] == []
        assert "myrm-memory" in data["config_json"]["mcpServers"]
        assert "myrm" not in data["config_json"]["mcpServers"]

    def test_generate_expose_desktop_true(self, client: TestClient):
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


class TestConnectDoctorAPI:
    """Test POST /connect/doctor endpoint."""

    def test_doctor_after_generate_returns_healthy(self, client: TestClient):
        client.post(f"{API_PREFIX}/connect/generate", json={"profile_id": "windsurf"})
        response = client.post(f"{API_PREFIX}/connect/doctor", json={"profile_id": "windsurf"})
        assert response.status_code == 200
        data = response.json()
        assert data["healthy"] is True
        assert data["detail"] == "token_valid"
        assert data["severity"] == "warn"

    def test_doctor_response_has_detail_field(self, client: TestClient):
        response = client.post(f"{API_PREFIX}/connect/doctor", json={"profile_id": "cursor"})
        assert response.status_code == 200
        assert "detail" in response.json()
        assert isinstance(response.json()["detail"], str)
        assert "severity" in response.json()

    def test_doctor_unconfigured_returns_unhealthy(self, client: TestClient):
        response = client.post(f"{API_PREFIX}/connect/doctor", json={"profile_id": "gemini_cli"})
        assert response.status_code == 200
        data = response.json()
        assert data["healthy"] is False
        assert data["detail"] == "unknown"


class TestConnectRevokeAPI:
    """Test POST /connect/revoke endpoint."""

    def test_revoke_configured_returns_true(self, client: TestClient):
        client.post(f"{API_PREFIX}/connect/generate", json={"profile_id": "claude_code"})
        response = client.post(f"{API_PREFIX}/connect/revoke", json={"profile_id": "claude_code"})
        assert response.status_code == 200
        assert response.json()["revoked"] is True

    def test_revoke_unknown_returns_false(self, client: TestClient):
        response = client.post(f"{API_PREFIX}/connect/revoke", json={"profile_id": "unknown_agent"})
        assert response.status_code == 200
        assert response.json()["revoked"] is False

    def test_revoke_invalidates_doctor(self, client: TestClient):
        client.post(f"{API_PREFIX}/connect/generate", json={"profile_id": "cursor"})
        client.post(f"{API_PREFIX}/connect/revoke", json={"profile_id": "cursor"})
        response = client.post(f"{API_PREFIX}/connect/doctor", json={"profile_id": "cursor"})
        assert response.json()["healthy"] is False


class TestConnectStatusAPI:
    """Test GET /connect/status endpoint."""

    def test_status_returns_200(self, client: TestClient):
        response = client.get(f"{API_PREFIX}/connect/status")
        assert response.status_code == 200

    def test_status_returns_all_connectors(self, client: TestClient):
        response = client.get(f"{API_PREFIX}/connect/status")
        data = response.json()
        assert len(data) == 5

    def test_status_fields(self, client: TestClient):
        response = client.get(f"{API_PREFIX}/connect/status")
        for item in response.json():
            assert "profile_id" in item
            assert "label" in item
            assert "status" in item
            assert "doctor_ok" in item
            assert "last_doctor_detail" in item
            assert "last_doctor_at" in item

    def test_status_last_doctor_at_after_doctor(self, client: TestClient):
        client.post(f"{API_PREFIX}/connect/generate", json={"profile_id": "cursor"})
        client.post(f"{API_PREFIX}/connect/doctor", json={"profile_id": "cursor"})
        response = client.get(f"{API_PREFIX}/connect/status")
        item = next(i for i in response.json() if i["profile_id"] == "cursor")
        assert item["last_doctor_at"] is not None
        assert item["last_doctor_detail"] == "token_valid"
        assert item["connected_at"] is None

    def test_status_returns_expose_desktop(self, client: TestClient):
        client.post(
            f"{API_PREFIX}/connect/generate",
            json={"profile_id": "windsurf", "expose_desktop": True},
        )
        response = client.get(f"{API_PREFIX}/connect/status")
        item = next(i for i in response.json() if i["profile_id"] == "windsurf")
        assert item["expose_desktop"] is True


class TestAgentPluginAPI:
    """Test POST /connect/agent-plugin endpoint."""

    def test_generate_bundle_returns_200(self, client: TestClient):
        response = client.post(f"{API_PREFIX}/connect/agent-plugin", json={"agent_id": "default"})
        assert response.status_code == 200

    def test_generate_bundle_file_set(self, client: TestClient):
        response = client.post(f"{API_PREFIX}/connect/agent-plugin", json={"agent_id": "default"})
        data = response.json()
        assert set(data["files"]) == {
            "plugin.json",
            "mcp.json",
            "skills/myrm-memory/SKILL.md",
        }

    def test_generate_bundle_fields(self, client: TestClient):
        response = client.post(
            f"{API_PREFIX}/connect/agent-plugin",
            json={"agent_id": "research-agent", "embed_token": False},
        )
        data = response.json()
        assert data["agent_id"] == "research-agent"
        assert data["embed_token"] is False
        assert data["token"].startswith("myrm_mcp_")
        assert data["mcp_url"].endswith("/mcp")
        assert "MYRM_MCP_TOKEN" in data["instructions"]

    def test_generate_embedded_token_default(self, client: TestClient):
        response = client.post(f"{API_PREFIX}/connect/agent-plugin", json={})
        data = response.json()
        # Default is env mode (spec-compliant, no credential in bundle files).
        assert data["embed_token"] is False

    def test_revoke_agent_plugin_through_api(self, client: TestClient):
        client.post(f"{API_PREFIX}/connect/agent-plugin", json={"agent_id": "default"})
        revoke = client.post(f"{API_PREFIX}/connect/revoke", json={"profile_id": "agent_plugin"})
        assert revoke.status_code == 200
        assert revoke.json()["revoked"] is True
        # The revoked token must no longer authenticate (doctor reports unhealthy).
        doctor = client.post(f"{API_PREFIX}/connect/doctor", json={"profile_id": "agent_plugin"})
        assert doctor.json()["healthy"] is False


class TestConnectAgentCapabilitiesAPI:
    """Test GET /connect/agent-capabilities/{agent_id} endpoint."""

    def test_agent_capabilities_not_found(self, client: TestClient):
        with patch(
            "app.services.agent.profile.profile_resolver.get_agent_profile_resolver"
        ) as mock_resolver_fn:
            mock_resolver = MagicMock()
            mock_resolver.resolve = AsyncMock(return_value=None)
            mock_resolver_fn.return_value = mock_resolver

            response = client.get(f"{API_PREFIX}/connect/agent-capabilities/nonexistent_agent")
            assert response.status_code == 200
            data = response.json()
            assert data["agent_id"] == "nonexistent_agent"
            assert data["has_computer_use"] is False
            assert data["can_expose_desktop"] is False

    def test_agent_capabilities_desktop_supported(self, client: TestClient):
        mock_profile = MagicMock()
        mock_profile.agent_id = "desk-agent"
        mock_profile.enabled_builtin_tools = ["computer_use"]

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
            assert data["desktop_deploy_supported"] is True
            assert data["can_expose_desktop"] is True

    def test_agent_capabilities_desktop_unsupported(self, client: TestClient):
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
