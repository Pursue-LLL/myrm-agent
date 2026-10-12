"""Browser connectivity API tests.

Covers ``/api/v1/health/browser/test-cloud-connection`` and ``/api/v1/health/browser/test-proxy-connection``:
unconfigured and disabled states, invalid input, and the success / failure outcome of each probe.
"""

import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(preset="health")


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _config_record(value: dict[str, object]) -> SimpleNamespace:
    """Build a minimal ConfigRecord-shaped object for config_service.get."""
    return SimpleNamespace(key="test", value=value, version="1")


@patch("app.services.config.service.config_service.get", return_value=None)
def test_cloud_connection_not_configured(
    _mock_get: object,
    client: TestClient,
) -> None:
    """POST /browser/test-cloud-connection without config must say so."""
    response = client.post("/api/v1/health/browser/test-cloud-connection")

    assert response.status_code == 200
    assert response.json()["status"] == "not_configured"


@patch("app.services.config.service.config_service.get")
def test_cloud_connection_disabled(
    mock_get: object,
    client: TestClient,
) -> None:
    """POST /browser/test-cloud-connection with a disabled provider."""
    mock_get.return_value = _config_record(  # type: ignore[attr-defined]
        {"enabled": False, "provider": "browserbase", "credential": "sk-test"}
    )

    response = client.post("/api/v1/health/browser/test-cloud-connection")

    assert response.status_code == 200
    assert response.json() == {
        "status": "disabled",
        "message": "Cloud browser provider is disabled",
    }


@patch("app.services.config.service.config_service.get")
def test_cloud_connection_invalid_endpoint(
    mock_get: object,
    client: TestClient,
) -> None:
    """POST /browser/test-cloud-connection without a credential cannot resolve a WS URL."""
    mock_get.return_value = _config_record(  # type: ignore[attr-defined]
        {"enabled": True, "provider": "browserbase", "credential": ""}
    )

    response = client.post("/api/v1/health/browser/test-cloud-connection")

    assert response.status_code == 200
    assert response.json()["status"] == "invalid"


@patch("app.services.config.service.config_service.get")
def test_cloud_connection_success_via_websockets(
    mock_get: object,
    client: TestClient,
) -> None:
    """POST /browser/test-cloud-connection reports connected after a WS handshake."""
    mock_get.return_value = _config_record(  # type: ignore[attr-defined]
        {"enabled": True, "provider": "browserbase", "credential": "sk-live"}
    )
    mock_ws_ctx = AsyncMock()
    mock_ws_ctx.__aenter__.return_value = mock_ws_ctx
    mock_websockets = MagicMock()
    mock_websockets.connect.return_value = mock_ws_ctx

    with patch.dict(sys.modules, {"websockets": mock_websockets}):
        response = client.post("/api/v1/health/browser/test-cloud-connection")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "connected"
    assert data["provider"] == "browserbase"
    assert "ms" in data["message"]


@patch("app.services.config.service.config_service.get")
def test_cloud_connection_failure_reports_error(
    mock_get: object,
    client: TestClient,
) -> None:
    """POST /browser/test-cloud-connection surfaces handshake failures."""
    mock_get.return_value = _config_record(  # type: ignore[attr-defined]
        {"enabled": True, "provider": "browserbase", "credential": "sk-live"}
    )
    mock_ws_ctx = AsyncMock()
    mock_ws_ctx.__aenter__.side_effect = ConnectionError("handshake refused")
    mock_websockets = MagicMock()
    mock_websockets.connect.return_value = mock_ws_ctx

    with patch.dict(sys.modules, {"websockets": mock_websockets}):
        response = client.post("/api/v1/health/browser/test-cloud-connection")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "failed"
    assert "handshake refused" in data["error"]


@patch("app.services.config.service.config_service.get")
def test_cloud_connection_no_ws_library(
    mock_get: object,
    client: TestClient,
) -> None:
    """POST /browser/test-cloud-connection reports error when no WS lib is installed."""
    mock_get.return_value = _config_record(  # type: ignore[attr-defined]
        {
            "enabled": True,
            "provider": "browserbase",
            "credential": "test-key",
        }
    )
    with patch.dict(
        sys.modules,
        {
            "websockets": None,
            "aiohttp": None,
        },
    ):
        response = client.post("/api/v1/health/browser/test-cloud-connection")

    assert response.status_code == 200
    assert response.json()["status"] == "error"
    assert "No WebSocket library" in response.json()["message"]


@patch("app.services.config.service.config_service.get", return_value=None)
def test_proxy_connection_not_configured(
    _mock_get: object,
    client: TestClient,
) -> None:
    """POST /browser/test-proxy-connection without config must say so."""
    response = client.post("/api/v1/health/browser/test-proxy-connection")

    assert response.status_code == 200
    assert response.json()["status"] == "not_configured"


@patch("app.services.config.service.config_service.get")
def test_proxy_connection_disabled(
    mock_get: object,
    client: TestClient,
) -> None:
    """POST /browser/test-proxy-connection with a disabled proxy."""
    mock_get.return_value = _config_record(  # type: ignore[attr-defined]
        {"enabled": False, "proxies": ["http://127.0.0.1:8888"]}
    )

    response = client.post("/api/v1/health/browser/test-proxy-connection")

    assert response.status_code == 200
    assert response.json() == {
        "status": "disabled",
        "message": "Browser proxy is disabled",
    }


@patch("app.services.config.service.config_service.get")
def test_proxy_connection_invalid_no_proxies(
    mock_get: object,
    client: TestClient,
) -> None:
    """POST /browser/test-proxy-connection with an empty proxy list."""
    mock_get.return_value = _config_record(  # type: ignore[attr-defined]
        {"enabled": True, "proxies": []}
    )

    response = client.post("/api/v1/health/browser/test-proxy-connection")

    assert response.status_code == 200
    assert response.json()["status"] == "invalid"


@patch("app.services.config.service.config_service.get")
def test_proxy_connection_success(
    mock_get: object,
    client: TestClient,
) -> None:
    """POST /browser/test-proxy-connection reports connected with egress IP."""
    mock_get.return_value = _config_record(  # type: ignore[attr-defined]
        {
            "enabled": True,
            "proxies": ["http://user:pass@127.0.0.1:8888", "http://127.0.0.1:9999"],
        }
    )
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"origin": "203.0.113.9"}
    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.get = AsyncMock(return_value=mock_response)

    with patch("app.api.health.browser.httpx.AsyncClient", return_value=mock_client):
        response = client.post("/api/v1/health/browser/test-proxy-connection")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "connected"
    assert data["proxy_count"] == 2
    assert data["egress_ip"] == "203.0.113.9"
    mock_client.get.assert_awaited_once_with("https://httpbin.org/ip")


@patch("app.services.config.service.config_service.get")
def test_proxy_connection_http_error(
    mock_get: object,
    client: TestClient,
) -> None:
    """POST /browser/test-proxy-connection reports non-200 responses as failed."""
    mock_get.return_value = _config_record(  # type: ignore[attr-defined]
        {"enabled": True, "proxies": ["http://127.0.0.1:8888"]}
    )
    mock_response = MagicMock()
    mock_response.status_code = 407
    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.get = AsyncMock(return_value=mock_response)

    with patch("app.api.health.browser.httpx.AsyncClient", return_value=mock_client):
        response = client.post("/api/v1/health/browser/test-proxy-connection")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "failed"
    assert data["error"] == "HTTP 407"


@patch("app.services.config.service.config_service.get")
def test_proxy_connection_exception(
    mock_get: object,
    client: TestClient,
) -> None:
    """POST /browser/test-proxy-connection surfaces transport exceptions."""
    mock_get.return_value = _config_record(  # type: ignore[attr-defined]
        {"enabled": True, "proxies": ["http://127.0.0.1:8888"]}
    )
    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.get = AsyncMock(side_effect=ConnectionError("proxy unreachable"))

    with patch("app.api.health.browser.httpx.AsyncClient", return_value=mock_client):
        response = client.post("/api/v1/health/browser/test-proxy-connection")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "failed"
    assert "proxy unreachable" in data["error"]
