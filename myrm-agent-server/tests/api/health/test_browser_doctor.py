"""Browser doctor API tests.

Covers ``/api/v1/health/browser/doctor`` and ``/api/v1/health/browser/orphans``:
- doctor endpoint injects the real server port into ``run_doctor`` (D2 regression)
- orphan list/cleanup endpoints use the unified automation scan and keep the
  ``confirm`` safety semantics (D1/D3 regression)
Also covers the remaining health/browser endpoints: ``/browser`` pool health,
``/browser/test-cloud-connection`` and ``/browser/test-proxy-connection``.
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


def _fake_report() -> SimpleNamespace:
    check = SimpleNamespace(
        status=SimpleNamespace(value="ok"),
        message="ok",
        fix=None,
        details={},
    )
    return SimpleNamespace(
        summary="All checks passed",
        overall_healthy=True,
        checks={"patchright": check},
        recommendations=[],
    )


@patch("app.lifecycle.browser.resolve_browser_proxy_pool", return_value=None)
@patch("myrm_agent_harness.toolkits.browser.run_doctor")
def test_browser_doctor_injects_real_server_port(
    mock_run_doctor: object,
    mock_proxy: object,
    client: TestClient,
) -> None:
    """The doctor endpoint must forward the actual server port as the relay base URL."""
    from app.config.settings import settings

    mock_run_doctor.return_value = _fake_report()  # type: ignore[attr-defined]

    response = client.get("/api/v1/health/browser/doctor")

    assert response.status_code == 200
    data = response.json()
    assert data["overall_healthy"] is True
    assert data["checks"]["patchright"]["status"] == "ok"
    mock_run_doctor.assert_called_once_with(  # type: ignore[attr-defined]
        include_launch_test=True,
        browser_proxy="",
        extension_relay_base_url=f"http://127.0.0.1:{settings.port}",
    )


@patch("app.lifecycle.browser.resolve_browser_proxy_pool", return_value=None)
@patch("myrm_agent_harness.toolkits.browser.run_doctor")
def test_browser_doctor_honors_launch_test_flag(
    mock_run_doctor: object,
    mock_proxy: object,
    client: TestClient,
) -> None:
    """``launch_test=false`` must be forwarded to disable the browser launch test."""
    from app.config.settings import settings

    mock_run_doctor.return_value = _fake_report()  # type: ignore[attr-defined]

    response = client.get("/api/v1/health/browser/doctor?launch_test=false")

    assert response.status_code == 200
    mock_run_doctor.assert_called_once_with(  # type: ignore[attr-defined]
        include_launch_test=False,
        browser_proxy="",
        extension_relay_base_url=f"http://127.0.0.1:{settings.port}",
    )


@patch("myrm_agent_harness.toolkits.browser.find_orphan_automation_processes")
def test_list_browser_orphans_uses_automation_scan(
    mock_find: object,
    client: TestClient,
) -> None:
    """GET /browser/orphans must surface the unified chromium + driver scan."""
    mock_find.return_value = [  # type: ignore[attr-defined]
        {"pid": 12345, "name": "Chromium", "user_data_dir": "/tmp/myrm-profile-1"},
        {"pid": 23456, "name": "node", "user_data_dir": "/tmp/myrm-profile-1"},
    ]

    response = client.get("/api/v1/health/browser/orphans")

    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 2
    assert [o["pid"] for o in data["orphans"]] == [12345, 23456]
    mock_find.assert_called_once_with()  # type: ignore[attr-defined]


@patch("myrm_agent_harness.toolkits.browser.find_orphan_automation_processes")
def test_cleanup_browser_orphans_without_confirm_is_dry_run(
    mock_find: object,
    client: TestClient,
) -> None:
    """DELETE without confirm=true must stay in dry-run mode (safety gate)."""
    mock_find.return_value = [  # type: ignore[attr-defined]
        {"pid": 12345, "name": "Chromium", "user_data_dir": "/tmp/myrm-profile-1"},
    ]

    with patch(
        "myrm_agent_harness.toolkits.browser.cleanup_orphan_processes",
        return_value={"killed": 0, "dry_run": True, "failed": []},
    ) as mock_cleanup:
        response = client.delete("/api/v1/health/browser/orphans")

    assert response.status_code == 200
    data = response.json()
    assert data["dry_run"] is True
    assert data["killed"] == 0
    mock_cleanup.assert_called_once_with([12345], force=False)


@patch("myrm_agent_harness.toolkits.browser.find_orphan_automation_processes")
def test_cleanup_browser_orphans_with_confirm_forces_kill(
    mock_find: object,
    client: TestClient,
) -> None:
    """DELETE with confirm=true must force cleanup and surface per-PID failures."""
    mock_find.return_value = [  # type: ignore[attr-defined]
        {"pid": 12345, "name": "Chromium", "user_data_dir": "/tmp/myrm-profile-1"},
        {"pid": 23456, "name": "node", "user_data_dir": "/tmp/myrm-profile-1"},
    ]

    with patch(
        "myrm_agent_harness.toolkits.browser.cleanup_orphan_processes",
        return_value={
            "killed": 1,
            "dry_run": False,
            "failed": [{"pid": 23456, "reason": "permission_denied"}],
        },
    ) as mock_cleanup:
        response = client.delete("/api/v1/health/browser/orphans?confirm=true")

    assert response.status_code == 200
    data = response.json()
    assert data["dry_run"] is False
    assert data["killed"] == 1
    assert data["failed"] == [{"pid": 23456, "reason": "permission_denied"}]
    mock_cleanup.assert_called_once_with([12345, 23456], force=True)


@patch("myrm_agent_harness.toolkits.browser.find_orphan_automation_processes")
def test_cleanup_browser_orphans_when_none_found(
    mock_find: object,
    client: TestClient,
) -> None:
    """DELETE with no orphans must return an empty result instead of erroring."""
    mock_find.return_value = []  # type: ignore[attr-defined]

    response = client.delete("/api/v1/health/browser/orphans?confirm=true")

    assert response.status_code == 200
    data = response.json()
    assert data["killed"] == 0
    assert data["orphans"] == []


def _config_record(value: dict[str, object]) -> SimpleNamespace:
    """Build a minimal ConfigRecord-shaped object for config_service.get."""
    return SimpleNamespace(key="test", value=value, version="1")


@patch("app.config.browser.get_configured_browser_pool")
def test_browser_health_returns_pool_status(
    mock_pool_get: object,
    client: TestClient,
) -> None:
    """GET /browser must surface the pool health dict verbatim."""
    mock_pool = MagicMock()
    mock_pool.health.return_value = {
        "status": "healthy",
        "active": 2,
        "total": 4,
    }
    mock_pool_get.return_value = mock_pool  # type: ignore[attr-defined]

    response = client.get("/api/v1/health/browser")

    assert response.status_code == 200
    assert response.json() == {"status": "healthy", "active": 2, "total": 4}


@patch("app.config.browser.get_configured_browser_pool")
def test_browser_health_returns_string_status(
    mock_pool_get: object,
    client: TestClient,
) -> None:
    """GET /browser must wrap a string health result into a status key."""
    mock_pool = MagicMock()
    mock_pool.health.return_value = "degraded"
    mock_pool_get.return_value = mock_pool  # type: ignore[attr-defined]

    response = client.get("/api/v1/health/browser")

    assert response.status_code == 200
    assert response.json() == {"status": "degraded"}


@patch("app.config.browser.get_configured_browser_pool")
def test_browser_health_degrades_on_exception(
    mock_pool_get: object,
    client: TestClient,
) -> None:
    """GET /browser must degrade to unhealthy when pool.health raises."""
    mock_pool = MagicMock()
    mock_pool.health.side_effect = RuntimeError("pool exploded")
    mock_pool_get.return_value = mock_pool  # type: ignore[attr-defined]

    response = client.get("/api/v1/health/browser")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "unhealthy"
    assert "pool exploded" in data["error"]
    assert "Failed to get browser pool health" in data["message"]


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


def test_cloud_connection_no_ws_library(
    client: TestClient,
) -> None:
    """POST /browser/test-cloud-connection reports error when no WS lib is installed."""
    with (
        patch("app.services.config.service.config_service.get"),
        patch.dict(
            sys.modules,
            {
                "websockets": None,
                "aiohttp": None,
            },
        ),
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
    mock_response = AsyncMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"origin": "203.0.113.9"}
    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.get.return_value = mock_response

    with patch("httpx.AsyncClient", return_value=mock_client):
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
    mock_response = AsyncMock()
    mock_response.status_code = 407
    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.get.return_value = mock_response

    with patch("httpx.AsyncClient", return_value=mock_client):
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
    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.get.side_effect = ConnectionError("proxy unreachable")

    with patch("httpx.AsyncClient", return_value=mock_client):
        response = client.post("/api/v1/health/browser/test-proxy-connection")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "failed"
    assert "proxy unreachable" in data["error"]
