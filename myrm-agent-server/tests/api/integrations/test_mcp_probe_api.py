"""HTTP tests for POST /api/v1/integrations/mcp/probe connectivity check endpoint."""

from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(preset="integrations")


@pytest.fixture
def client() -> Iterator[TestClient]:
    with patch(
        "app.core.security.auth.identity.is_loopback_ip",
        return_value=True,
    ):
        yield TestClient(app)


class TestMCPProbeEndpoint:
    """POST /api/v1/integrations/mcp/probe — connectivity probe for local MCP servers."""

    def test_probe_reachable(self, client: TestClient) -> None:
        """Probe returns reachable when target responds."""
        mock_response = AsyncMock()
        mock_response.status_code = 200

        with patch("httpx.AsyncClient.get", return_value=mock_response):
            response = client.post(
                "/api/v1/integrations/mcp/probe",
                json={"url": "http://127.0.0.1:8000/mcp", "timeout": 3},
            )

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["status"] == "reachable"
        assert data["latencyMs"] is not None

    def test_probe_unreachable_connect_error(self, client: TestClient) -> None:
        """Probe returns unreachable on connection refused."""
        import httpx

        with patch("httpx.AsyncClient.get", side_effect=httpx.ConnectError("Connection refused")):
            response = client.post(
                "/api/v1/integrations/mcp/probe",
                json={"url": "http://127.0.0.1:8000/mcp"},
            )

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["status"] == "unreachable"
        assert "not running" in data["error"]

    def test_probe_unreachable_timeout(self, client: TestClient) -> None:
        """Probe returns unreachable on connection timeout."""
        import httpx

        with patch("httpx.AsyncClient.get", side_effect=httpx.ConnectTimeout("timed out")):
            response = client.post(
                "/api/v1/integrations/mcp/probe",
                json={"url": "http://127.0.0.1:9876/sse"},
            )

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["status"] == "unreachable"
        assert "timed out" in data["error"]

    def test_probe_cloud_not_supported(self, client: TestClient) -> None:
        """Probe returns cloud_not_supported in sandbox deployment."""
        from app.platform_utils.deployment_capabilities import DeploymentCapabilities

        sandbox_caps = DeploymentCapabilities(
            allows_local_skills=False,
            requires_api_key_auth=True,
            uses_platform_budget=True,
            validates_mcp_response_size=True,
            uses_config_encryption=True,
            requires_strict_ws_auth=True,
            uses_cp_entitlements=True,
            trust_cp_proxy_identity=True,
            enables_auth_audit=True,
            default_metrics_enabled=False,
            runs_sandbox_startup_validation=True,
            skips_webui_model_preflight=True,
            is_sandbox_instance=True,
        )

        with patch(
            "app.api.integrations.mcp.get_deployment_capabilities",
            return_value=sandbox_caps,
        ):
            response = client.post(
                "/api/v1/integrations/mcp/probe",
                json={"url": "http://127.0.0.1:8000/mcp"},
            )

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["status"] == "cloud_not_supported"

    def test_probe_validation_timeout_range(self, client: TestClient) -> None:
        """Timeout must be between 1 and 15 seconds."""
        response = client.post(
            "/api/v1/integrations/mcp/probe",
            json={"url": "http://127.0.0.1:8000/mcp", "timeout": 0.5},
        )
        assert response.status_code == 422

        response = client.post(
            "/api/v1/integrations/mcp/probe",
            json={"url": "http://127.0.0.1:8000/mcp", "timeout": 20},
        )
        assert response.status_code == 422

    def test_probe_url_required(self, client: TestClient) -> None:
        """URL field is mandatory."""
        response = client.post(
            "/api/v1/integrations/mcp/probe",
            json={"timeout": 5},
        )
        assert response.status_code == 422

    def test_probe_rejects_non_localhost(self, client: TestClient) -> None:
        """Probe must reject non-localhost URLs to prevent SSRF."""
        response = client.post(
            "/api/v1/integrations/mcp/probe",
            json={"url": "http://evil.com:8000/mcp"},
        )
        assert response.status_code == 400
