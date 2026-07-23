"""HTTP tests for POST /api/v1/integrations/mcp/probe connectivity check endpoint."""

from __future__ import annotations

import errno
import ssl
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
        assert data["reasonCode"] == "reachable"
        assert data.get("recommendedMode") is None
        assert data["shouldBlockConnect"] is False

    def test_probe_does_not_disable_tls_verification(self, client: TestClient) -> None:
        """Probe must not pass verify=False to AsyncClient."""
        verify_values: list[object] = []

        class _FakeAsyncClient:
            def __init__(self, *args: object, **kwargs: object) -> None:
                verify_values.append(kwargs.get("verify", "__default__"))

            async def __aenter__(self) -> "_FakeAsyncClient":
                return self

            async def __aexit__(self, exc_type: object, exc: object, tb: object) -> bool:
                return False

            async def get(self, _url: str) -> AsyncMock:
                response = AsyncMock()
                response.status_code = 200
                return response

        with patch("httpx.AsyncClient", _FakeAsyncClient):
            response = client.post(
                "/api/v1/integrations/mcp/probe",
                json={"url": "http://127.0.0.1:8000/mcp", "timeout": 3},
            )

        assert response.status_code == 200
        assert verify_values
        assert verify_values[0] is not False

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
        assert data["reasonCode"] == "connection_refused"
        assert data["recommendedMode"] == "start_local_editor_mcp"
        assert data["shouldBlockConnect"] is True

    def test_probe_unreachable_connect_error_network_unreachable(self, client: TestClient) -> None:
        """Probe maps route-level failures to verify_local_network_and_editor."""
        import httpx

        async def _raise_network_unreachable(_url: str) -> None:
            try:
                raise OSError(errno.EHOSTUNREACH, "No route to host")
            except OSError as os_exc:
                raise httpx.ConnectError("No route to host") from os_exc

        with patch("httpx.AsyncClient.get", side_effect=_raise_network_unreachable):
            response = client.post(
                "/api/v1/integrations/mcp/probe",
                json={"url": "http://127.0.0.1:8000/mcp"},
            )

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["status"] == "unreachable"
        assert "network route unavailable" in data["error"]
        assert data["reasonCode"] == "connection_unreachable"
        assert data["recommendedMode"] == "verify_local_network_and_editor"
        assert data["shouldBlockConnect"] is True

    def test_probe_unreachable_tls_verification_error(self, client: TestClient) -> None:
        """Probe returns a dedicated reason code for TLS certificate failures."""
        import httpx

        with patch(
            "httpx.AsyncClient.get",
            side_effect=httpx.ConnectError(
                "[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: self signed certificate"
            ),
        ):
            response = client.post(
                "/api/v1/integrations/mcp/probe",
                json={"url": "http://127.0.0.1:8000/mcp"},
            )

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["status"] == "unreachable"
        assert "certificate" in data["error"].lower()
        assert data["reasonCode"] == "tls_verification_failed"
        assert data.get("recommendedMode") is None
        assert data["shouldBlockConnect"] is True

    def test_probe_unreachable_tls_verification_error_from_ssl_cause(
        self, client: TestClient
    ) -> None:
        """Probe classifies wrapped SSLCertVerificationError as TLS verification failure."""
        import httpx

        async def _raise_ssl_connect_error(_url: str) -> None:
            try:
                raise ssl.SSLCertVerificationError("certificate verify failed")
            except ssl.SSLCertVerificationError as ssl_exc:
                raise httpx.ConnectError("ssl handshake failed") from ssl_exc

        with patch("httpx.AsyncClient.get", side_effect=_raise_ssl_connect_error):
            response = client.post(
                "/api/v1/integrations/mcp/probe",
                json={"url": "http://127.0.0.1:8000/mcp"},
            )

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["status"] == "unreachable"
        assert data["reasonCode"] == "tls_verification_failed"
        assert data["shouldBlockConnect"] is True

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
        assert data["reasonCode"] == "connection_timeout"
        assert data["recommendedMode"] == "verify_local_network_and_editor"
        assert data["shouldBlockConnect"] is True

    def test_probe_cloud_not_supported(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Probe returns cloud_not_supported when runtime deploy mode is sandbox."""
        from app.config.deploy_mode import get_deploy_mode
        from app.platform_utils.deployment_capabilities import (
            _reset_capabilities_cache_for_testing,
        )

        monkeypatch.setenv("DEPLOY_MODE", "sandbox")
        get_deploy_mode.cache_clear()
        _reset_capabilities_cache_for_testing()
        try:
            with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
                response = client.post(
                    "/api/v1/integrations/mcp/probe",
                    json={"url": "http://127.0.0.1:8000/mcp"},
                )

            assert response.status_code == 200
            data = response.json()["data"]
            assert data["status"] == "cloud_not_supported"
            assert data["reasonCode"] == "loopback_unavailable_in_cloud"
            assert data["recommendedMode"] == "local_or_tauri"
            assert data["shouldBlockConnect"] is True
            mock_get.assert_not_called()
        finally:
            get_deploy_mode.cache_clear()
            _reset_capabilities_cache_for_testing()

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

    def test_probe_unreachable_generic_error(self, client: TestClient) -> None:
        """Probe returns a sanitized generic error on unexpected exceptions."""
        import httpx

        with patch("httpx.AsyncClient.get", side_effect=httpx.ReadError("broken pipe")):
            response = client.post(
                "/api/v1/integrations/mcp/probe",
                json={"url": "http://127.0.0.1:8000/mcp"},
            )

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["status"] == "unreachable"
        assert data["error"] == "Connectivity check failed unexpectedly — verify editor MCP settings and retry"
        assert "broken pipe" not in data["error"]
        assert data["reasonCode"] == "probe_failed_unknown"
        assert data["recommendedMode"] == "verify_local_network_and_editor"
        assert data["shouldBlockConnect"] is True

    def test_probe_unreachable_generic_error_logs_sanitized_target(self, client: TestClient) -> None:
        """Probe logging must drop credentials and query parameters from target URL."""
        import httpx

        with (
            patch("httpx.AsyncClient.get", side_effect=httpx.ReadError("broken pipe")),
            patch("app.api.integrations.mcp.logger.exception") as mock_logger_exception,
        ):
            response = client.post(
                "/api/v1/integrations/mcp/probe",
                json={"url": "http://user:secret@127.0.0.1:8000/mcp?token=abc"},
            )

        assert response.status_code == 200
        mock_logger_exception.assert_called_once_with(
            "Unexpected MCP probe failure for target=%s",
            "http://127.0.0.1:8000/mcp",
        )
