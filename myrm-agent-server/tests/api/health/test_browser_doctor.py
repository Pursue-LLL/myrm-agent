"""Browser doctor API tests.

Covers ``/api/v1/health/browser/doctor`` and ``/api/v1/health/browser/orphans``:
- doctor endpoint hands the server-owned extension relay check to ``run_doctor`` as an extra check,
  so the relay row is part of the report and of its summary
- orphan list/cleanup endpoints use the unified automation scan and keep the
  ``confirm`` safety semantics (D1/D3 regression)
Also covers the remaining health/browser endpoints: ``/browser`` pool health (dict or degraded),
``/browser/test-cloud-connection`` and ``/browser/test-proxy-connection``.
"""

import logging
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from myrm_agent_harness.toolkits.browser.doctor import CheckStatus, DoctorCheckResult

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


_RELAY_CHECK = "app.services.extension.relay_check.check_extension_relay"


@patch("app.lifecycle.browser.resolve_browser_proxy_pool", return_value=None)
@patch("myrm_agent_harness.toolkits.browser.run_doctor")
def test_browser_doctor_passes_the_extension_relay_check_to_run_doctor(
    mock_run_doctor: object,
    mock_proxy: object,
    client: TestClient,
) -> None:
    """The relay probe is server-owned, so the endpoint supplies it as an extra check."""
    mock_run_doctor.return_value = _fake_report()  # type: ignore[attr-defined]

    with patch(_RELAY_CHECK, new=MagicMock(return_value="relay-check")):
        response = client.get("/api/v1/health/browser/doctor")

    assert response.status_code == 200
    data = response.json()
    assert data["overall_healthy"] is True
    assert data["checks"]["patchright"]["status"] == "ok"
    mock_run_doctor.assert_called_once_with(  # type: ignore[attr-defined]
        include_launch_test=True,
        browser_proxy="",
        extra_checks={"extension_relay": "relay-check"},
    )


@patch("app.lifecycle.browser.resolve_browser_proxy_pool", return_value=None)
@patch("myrm_agent_harness.toolkits.browser.run_doctor")
def test_browser_doctor_honors_launch_test_flag(
    mock_run_doctor: object,
    mock_proxy: object,
    client: TestClient,
) -> None:
    """``launch_test=false`` must be forwarded to disable the browser launch test."""
    mock_run_doctor.return_value = _fake_report()  # type: ignore[attr-defined]

    with patch(_RELAY_CHECK, new=MagicMock(return_value="relay-check")):
        response = client.get("/api/v1/health/browser/doctor?launch_test=false")

    assert response.status_code == 200
    assert mock_run_doctor.call_args.kwargs["include_launch_test"] is False  # type: ignore[attr-defined]


@patch("app.lifecycle.browser.resolve_browser_proxy_pool", return_value=None)
@patch(
    "myrm_agent_harness.toolkits.browser.doctor.checks.check_orphan_processes",
    return_value=DoctorCheckResult(name="orphan_processes", status=CheckStatus.OK, message="clean"),
)
def test_browser_doctor_report_contains_the_extension_relay_row(
    _mock_orphans: object,
    _mock_proxy: object,
    client: TestClient,
) -> None:
    """Through the real orchestrator the relay row lands in ``checks`` and is counted by ``summary``."""
    relay = DoctorCheckResult(
        name="extension_relay",
        status=CheckStatus.WARNING,
        message="not connected",
        details={"optional": True},
    )

    with patch(_RELAY_CHECK, new=AsyncMock(return_value=relay)):
        response = client.get("/api/v1/health/browser/doctor?launch_test=false")

    assert response.status_code == 200
    data = response.json()
    assert data["checks"]["extension_relay"]["status"] == "warning"
    assert data["checks"]["extension_relay"]["details"] == {"optional": True}
    assert f"/{len(data['checks'])} checks passed" in data["summary"]


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
    assert "sandboxes_pruned" in data
    assert "reclaimed_bytes" in data


@patch(
    "myrm_agent_harness.toolkits.browser.find_orphan_automation_processes",
    side_effect=RuntimeError("scan exploded"),
)
def test_cleanup_browser_orphans_logs_the_root_cause_before_failing(
    _mock_find: object,
    client: TestClient,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The 500 detail stays generic for the client, so the real cause must reach the server log."""
    with caplog.at_level(logging.ERROR, logger="app.api.health.browser"):
        response = client.delete("/api/v1/health/browser/orphans?confirm=true")

    assert response.status_code == 500
    assert any(record.exc_info is not None and "scan exploded" in str(record.exc_info[1]) for record in caplog.records)


@patch("myrm_agent_harness.toolkits.browser.cleanup_stale_automation_sandboxes")
@patch("myrm_agent_harness.toolkits.browser.cleanup_orphan_processes")
@patch("myrm_agent_harness.toolkits.browser.find_orphan_automation_processes")
def test_cleanup_browser_orphans_prunes_sandboxes_and_reports_bytes(
    mock_find: object,
    mock_cleanup: object,
    mock_sandbox_cleanup: object,
    client: TestClient,
) -> None:
    """DELETE with confirm=true prunes sandboxes and returns disk space reclaimed."""
    mock_find.return_value = [{"pid": 9999, "name": "Chromium"}]  # type: ignore[attr-defined]
    mock_cleanup.return_value = {"killed": 1, "dry_run": False, "failed": []}  # type: ignore[attr-defined]
    mock_sandbox_cleanup.return_value = {  # type: ignore[attr-defined]
        "pruned": 5,
        "reclaimed_bytes": 104857600,
        "failed": [],
        "dry_run": False,
    }

    response = client.delete("/api/v1/health/browser/orphans?confirm=true")

    assert response.status_code == 200
    data = response.json()
    assert data["killed"] == 1
    assert data["sandboxes_pruned"] == 5
    assert data["reclaimed_bytes"] == 104857600
    assert "pruned 5 sandbox(es) (100.0 MB reclaimed)" in data["message"]


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
    mock_pool.health = AsyncMock(
        return_value={
            "status": "healthy",
            "active": 2,
            "total": 4,
        }
    )
    mock_pool_get.return_value = mock_pool  # type: ignore[attr-defined]

    response = client.get("/api/v1/health/browser")

    assert response.status_code == 200
    assert response.json() == {"status": "healthy", "active": 2, "total": 4}


@patch("app.config.browser.get_configured_browser_pool")
def test_browser_health_degrades_on_exception(
    mock_pool_get: object,
    client: TestClient,
) -> None:
    """GET /browser must degrade to unhealthy when pool.health raises."""
    mock_pool = MagicMock()
    mock_pool.health = AsyncMock(side_effect=RuntimeError("pool exploded"))
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
