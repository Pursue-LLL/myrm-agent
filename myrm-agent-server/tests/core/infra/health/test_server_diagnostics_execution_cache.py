"""Tests for ExecutionCacheDiagnostic and ServerDiagnosticsManager."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from myrm_agent_harness.observability.diagnostics.protocols import HealthReport

from app.core.infra.health.server_diagnostics import (
    ExecutionCacheDiagnostic,
    ServerDiagnosticsManager,
    run_server_diagnostics,
)


@pytest.mark.asyncio
async def test_execution_cache_diagnostic_success() -> None:
    probe = ExecutionCacheDiagnostic()

    mock_cache = MagicMock()
    mock_cache.idle_seconds = 1800.0
    mock_cache.warm_entry_count = 3
    mock_cache.reclaimed_count = 5

    with patch(
        "app.services.agent.execution_cache.get_execution_cache",
        return_value=mock_cache,
    ):
        report = await probe.check_health()
        assert isinstance(report, HealthReport)
        assert report.component_name == "ExecutionCache"
        assert report.status == "pass"
        assert report.code == "OK_EXECUTION_CACHE_ACTIVE"
        assert "warm units" in report.message
        assert report.meta_data is not None
        assert report.meta_data["idle_timeout_seconds"] == 1800.0
        assert report.meta_data["warm_entry_count"] == 3
        assert report.meta_data["reclaimed_count"] == 5


@pytest.mark.asyncio
async def test_execution_cache_diagnostic_disabled_idle() -> None:
    probe = ExecutionCacheDiagnostic()

    mock_cache = MagicMock()
    mock_cache.idle_seconds = 0.0
    mock_cache.warm_entry_count = 0
    mock_cache.reclaimed_count = 0

    with patch(
        "app.services.agent.execution_cache.get_execution_cache",
        return_value=mock_cache,
    ):
        report = await probe.check_health()
        assert report.status == "pass"
        assert "Idle reclaim disabled" in (report.detail or "")


@pytest.mark.asyncio
async def test_execution_cache_diagnostic_handles_exception() -> None:
    probe = ExecutionCacheDiagnostic()

    with patch(
        "app.services.agent.execution_cache.get_execution_cache",
        side_effect=RuntimeError("Cache failure"),
    ):
        report = await probe.check_health()
        assert report.component_name == "ExecutionCache"
        assert report.code == "WARN_EXECUTION_CACHE_DEGRADED"
        assert "Cache failure" in (report.detail or "")


@pytest.mark.asyncio
async def test_server_diagnostics_manager_runs_all() -> None:
    manager = ServerDiagnosticsManager()
    reports = await manager.run_all()
    assert len(reports) >= 6
    component_names = {r.component_name for r in reports}
    assert "ExecutionCache" in component_names
    assert "DLQ" in component_names


@pytest.mark.asyncio
async def test_run_server_diagnostics_shortcut() -> None:
    reports = await run_server_diagnostics()
    assert isinstance(reports, list)
    assert len(reports) >= 6
