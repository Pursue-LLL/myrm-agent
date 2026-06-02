"""Integration tests for Connect API router.

Tests the full API flow: list profiles, generate config, doctor, revoke,
and status endpoints using FastAPI TestClient.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app as _app

API_PREFIX = "/api/v1"


@pytest.fixture(scope="module")
def client():
    """Create test client from the real application."""
    import app.services.connect.service as svc
    svc._service = None
    return TestClient(_app)


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
        response = client.post(
            f"{API_PREFIX}/connect/generate", json={"profile_id": "claude_code"}
        )
        assert response.status_code == 200

    def test_generate_returns_token(self, client: TestClient):
        response = client.post(
            f"{API_PREFIX}/connect/generate", json={"profile_id": "cursor"}
        )
        data = response.json()
        assert data["token"].startswith("myrm_mcp_")
        assert data["mcp_url"].endswith("/mcp")
        assert "mcpServers" in data["config_json"]
        assert data["instructions"]

    def test_generate_unknown_profile_returns_error(self, client: TestClient):
        response = client.post(
            f"{API_PREFIX}/connect/generate", json={"profile_id": "nonexistent"}
        )
        assert response.status_code in (400, 422, 500)

    def test_generate_codex_returns_toml(self, client: TestClient):
        response = client.post(
            f"{API_PREFIX}/connect/generate", json={"profile_id": "codex"}
        )
        data = response.json()
        assert data["config_json"]["_format"] == "toml"
        assert "[mcp_servers.myrm-memory]" in data["config_json"]["_toml_snippet"]


class TestConnectDoctorAPI:
    """Test POST /connect/doctor endpoint."""

    def test_doctor_after_generate_returns_healthy(self, client: TestClient):
        client.post(f"{API_PREFIX}/connect/generate", json={"profile_id": "windsurf"})
        response = client.post(f"{API_PREFIX}/connect/doctor", json={"profile_id": "windsurf"})
        assert response.status_code == 200
        assert response.json()["healthy"] is True

    def test_doctor_unconfigured_returns_unhealthy(self, client: TestClient):
        response = client.post(f"{API_PREFIX}/connect/doctor", json={"profile_id": "gemini_cli"})
        assert response.status_code == 200
        assert response.json()["healthy"] is False


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
