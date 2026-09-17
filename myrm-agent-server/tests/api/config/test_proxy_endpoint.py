"""Tests for /test-proxy endpoint in config router."""

from __future__ import annotations

import http.server
import threading
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(preset="config")
client = TestClient(app)


def test_proxy_invalid_scheme() -> None:
    """Test that an invalid proxy URL schema returns success=False."""
    response = client.post(
        "/api/v1/config/test-proxy",
        json={"proxy_url": "ftp://invalid-scheme:8080"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is False
    assert "Unsupported proxy scheme" in data["error"] or "Invalid" in data["error"]


def test_proxy_empty_url() -> None:
    """Test that an empty proxy URL returns success=False."""
    response = client.post(
        "/api/v1/config/test-proxy",
        json={"proxy_url": "   "},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is False
    assert "cannot be empty" in data["error"]


@patch("myrm_agent_harness.toolkits.llms.utils.proxy.probe_proxy_health", new_callable=AsyncMock)
def test_proxy_probe_success(mock_probe: AsyncMock) -> None:
    """Test that a healthy proxy returns success=True with latency."""
    mock_probe.return_value = (True, None)

    response = client.post(
        "/api/v1/config/test-proxy",
        json={"proxy_url": "http://127.0.0.1:7890"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["error"] is None
    assert isinstance(data["latency_ms"], int)


@patch("myrm_agent_harness.toolkits.llms.utils.proxy.probe_proxy_health", new_callable=AsyncMock)
def test_proxy_probe_failure(mock_probe: AsyncMock) -> None:
    """Test that an unreachable proxy returns success=False with error message."""
    mock_probe.return_value = (False, "Proxy connection timed out")

    response = client.post(
        "/api/v1/config/test-proxy",
        json={"proxy_url": "socks5://10.255.255.1:1080"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is False
    assert data["error"] == "Proxy connection timed out"
    assert data["latency_ms"] is None


@patch("myrm_agent_harness.toolkits.llms.utils.proxy.probe_proxy_health", new_callable=AsyncMock)
def test_proxy_probe_custom_target_url(mock_probe: AsyncMock) -> None:
    """Test that a custom target URL is forwarded to probe_proxy_health."""
    mock_probe.return_value = (True, None)

    response = client.post(
        "/api/v1/config/test-proxy",
        json={
            "proxy_url": "http://127.0.0.1:7890",
            "target_url": "https://api.openai.com/v1",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    mock_probe.assert_called_once_with(
        proxy_url="http://127.0.0.1:7890",
        target_url="https://api.openai.com/v1",
        timeout_s=5.0,
        cache_ttl_s=0.0,
    )


# ---------------------------------------------------------------------------
# Real Full-Path Integration Tests (Zero Mocking on Critical Path)
# ---------------------------------------------------------------------------


class _RealTestProxyHandler(http.server.BaseHTTPRequestHandler):
    """Minimal real HTTP proxy handler for live integration testing."""

    def do_HEAD(self) -> None:
        self.send_response(200)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", "2")
        self.end_headers()
        self.wfile.write(b"OK")

    def do_CONNECT(self) -> None:
        self.send_response(200, "Connection Established")
        self.end_headers()

    def log_message(self, format: str, *args: object) -> None:
        """Suppress stdout/stderr log output during pytest execution."""


def test_proxy_endpoint_real_ssrf_metadata_blocked() -> None:
    """Real integration: proxy pointing to 169.254.169.254 is rejected by SSRF filter."""
    response = client.post(
        "/api/v1/config/test-proxy",
        json={"proxy_url": "http://169.254.169.254:80"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is False
    assert data["latency_ms"] is None
    assert "link-local address, which is blocked" in str(data["error"])


def test_proxy_endpoint_real_target_ssrf_blocked() -> None:
    """Real integration: probe target pointing to cloud metadata is rejected."""
    response = client.post(
        "/api/v1/config/test-proxy",
        json={
            "proxy_url": "http://127.0.0.1:8080",
            "target_url": "http://169.254.169.254/latest/meta-data",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is False
    assert data["latency_ms"] is None
    assert "Probe target URL blocked" in str(data["error"])
    assert "link-local address, which is blocked" in str(data["error"])


def test_proxy_endpoint_real_unreachable_connection_failure() -> None:
    """Real integration: unreachable proxy port fails with real network connection error."""
    # Port 59199 is bound to loopback and not listening, guaranteeing fast connection refusal
    response = client.post(
        "/api/v1/config/test-proxy",
        json={
            "proxy_url": "http://127.0.0.1:59199",
            "target_url": "http://127.0.0.1:59198",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is False
    assert data["latency_ms"] is None
    assert data["error"] is not None
    assert "refused" in data["error"].lower() or "connect" in data["error"].lower()


def test_proxy_endpoint_real_local_proxy_success() -> None:
    """Real integration: live HTTP proxy receives probe and responds with 200 OK."""
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _RealTestProxyHandler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    try:
        host, port = server.server_address
        proxy_url = f"http://{host}:{port}"
        target_url = f"http://{host}:{port}/probe"

        response = client.post(
            "/api/v1/config/test-proxy",
            json={
                "proxy_url": proxy_url,
                "target_url": target_url,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["error"] is None
        assert isinstance(data["latency_ms"], int)
        assert data["latency_ms"] >= 0
    finally:
        server.shutdown()
        server.server_close()

