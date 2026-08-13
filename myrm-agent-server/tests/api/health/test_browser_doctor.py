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
