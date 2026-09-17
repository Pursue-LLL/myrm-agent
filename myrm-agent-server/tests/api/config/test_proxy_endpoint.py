"""Tests for /test-proxy endpoint in config router."""

from __future__ import annotations

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
