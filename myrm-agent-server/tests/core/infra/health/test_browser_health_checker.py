"""Unit tests for app.core.infra.health.browser — BrowserHealthChecker."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from myrm_agent_harness.infra.health.health_checker import HealthStatus, RecoveryStatus

from app.core.infra.health.browser import BrowserHealthChecker


@pytest.mark.asyncio
async def test_check_healthy_no_orphans() -> None:
    checker = BrowserHealthChecker()
    with patch(
        "app.core.infra.health.browser.find_orphan_automation_processes",
        return_value=[],
    ):
        result = await checker.check()
        assert result.status == HealthStatus.HEALTHY
        assert "No orphan browser or driver processes found" in result.message


@pytest.mark.asyncio
async def test_check_unhealthy_with_orphans() -> None:
    checker = BrowserHealthChecker()
    orphans = [
        {"pid": 1234, "name": "chrome", "ppid": 1, "user_data_dir": "/path/to/.cache/patchright"},
        {"pid": 1235, "name": "node", "ppid": 1, "user_data_dir": ""},
    ]
    with patch(
        "app.core.infra.health.browser.find_orphan_automation_processes",
        return_value=orphans,
    ):
        result = await checker.check()
        assert result.status == HealthStatus.UNHEALTHY
        assert "Found 2 orphan browser/driver process(es)" in result.message
        assert result.details is not None
        assert result.details["orphan_pids"] == [1234, 1235]
        assert result.details["total_count"] == 2


@pytest.mark.asyncio
async def test_check_psutil_none() -> None:
    checker = BrowserHealthChecker()
    with patch("app.core.infra.health.browser.psutil", None):
        result = await checker.check()
        assert result.status == HealthStatus.UNKNOWN
        assert "psutil not available" in result.message


@pytest.mark.asyncio
async def test_recover_no_orphans() -> None:
    checker = BrowserHealthChecker()
    with patch(
        "app.core.infra.health.browser.find_orphan_automation_processes",
        return_value=[],
    ):
        result = await checker.recover()
        assert result.status == RecoveryStatus.SUCCESS
        assert "No orphan processes found" in result.message
        assert result.actions_taken == ["No recovery actions needed"]


@pytest.mark.asyncio
async def test_recover_psutil_none() -> None:
    checker = BrowserHealthChecker()
    with patch("app.core.infra.health.browser.psutil", None):
        result = await checker.recover()
        assert result.status == RecoveryStatus.NOT_ATTEMPTED
        assert "psutil not available" in result.message


@pytest.mark.asyncio
async def test_recover_success() -> None:
    checker = BrowserHealthChecker()
    orphans = [{"pid": 4321, "name": "chromium", "ppid": 1, "user_data_dir": "/tmp/.cache/patchright"}]
    with (
        patch(
            "app.core.infra.health.browser.find_orphan_automation_processes",
            side_effect=[orphans, []],
        ),
        patch(
            "app.core.infra.health.browser.cleanup_orphan_processes",
            return_value={"killed": 1, "dry_run": False},
        ) as mock_cleanup,
    ):
        result = await checker.recover()
        assert result.status == RecoveryStatus.SUCCESS
        assert "terminated 1 orphan process(es)" in result.message
        mock_cleanup.assert_called_once_with([4321], force=True)


@pytest.mark.asyncio
async def test_recover_partial() -> None:
    checker = BrowserHealthChecker()
    initial_orphans = [
        {"pid": 101, "name": "chromium", "ppid": 1},
        {"pid": 102, "name": "chromium", "ppid": 1},
    ]
    remaining_orphans = [{"pid": 102, "name": "chromium", "ppid": 1}]
    with (
        patch(
            "app.core.infra.health.browser.find_orphan_automation_processes",
            side_effect=[initial_orphans, remaining_orphans],
        ),
        patch(
            "app.core.infra.health.browser.cleanup_orphan_processes",
            return_value={"killed": 1, "dry_run": False},
        ),
    ):
        result = await checker.recover()
        assert result.status == RecoveryStatus.PARTIAL
        assert "Partial recovery: 1 killed, 1 remain" in result.message
        assert result.details is not None
        assert result.details["remaining_orphans"] == [102]


@pytest.mark.asyncio
async def test_recover_failed() -> None:
    checker = BrowserHealthChecker()
    orphans = [{"pid": 555, "name": "chromium", "ppid": 1}]
    with (
        patch(
            "app.core.infra.health.browser.find_orphan_automation_processes",
            return_value=orphans,
        ),
        patch(
            "app.core.infra.health.browser.cleanup_orphan_processes",
            return_value={"killed": 0, "dry_run": False},
        ),
    ):
        result = await checker.recover()
        assert result.status == RecoveryStatus.FAILED
        assert "Failed to terminate any orphan processes" in result.message
