"""Unit tests for Server business diagnostic probes, including AgentColdStartDiagnostic."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.infra.health.server_diagnostics import (
    AgentColdStartDiagnostic,
    ServerDiagnosticsManager,
    run_server_diagnostics,
)


@pytest.mark.asyncio
async def test_agent_cold_start_diagnostic_fully_ready() -> None:
    """Test AgentColdStartDiagnostic when all phases are primed and available."""
    diagnostic = AgentColdStartDiagnostic()

    mock_configs = SimpleNamespace(model_cfg=SimpleNamespace(model="test-gpt-4o"))

    mock_cache = MagicMock()
    mock_cache.warm_entry_count = 2

    with (
        patch("app.core.channel_bridge.config_loader.load_user_configs", AsyncMock(return_value=mock_configs)),
        patch("myrm_agent_harness.agent.tool_management.tool_layers.is_registered_action_tool", return_value=True),
        patch("app.services.agent.execution_cache.get_execution_cache", return_value=mock_cache),
        patch("app.database.connection.get_session") as mock_get_session,
    ):
        mock_session_ctx = MagicMock()
        mock_session = MagicMock()

        async def _fake_execute(*args, **kwargs):
            return 1

        mock_session.execute = _fake_execute
        mock_session_ctx.__aenter__.return_value = mock_session
        mock_session_ctx.__aexit__.return_value = None
        mock_get_session.return_value = mock_session_ctx

        report = await diagnostic.check_health()

        assert report.component_name == "AgentColdStart"
        assert report.status == "pass"
        assert report.code == "OK_AGENT_WARM_PATH_WARM"
        assert report.meta_data is not None
        assert report.meta_data["warm_path_score"] == 100
        assert "model_ready" in report.meta_data["ready_phases"]
        assert "tools_ready" in report.meta_data["ready_phases"]
        assert "cache_warm" in report.meta_data["ready_phases"]
        assert "storage_healthy" in report.meta_data["ready_phases"]
        assert report.fix_suggestion is None


@pytest.mark.asyncio
async def test_agent_cold_start_diagnostic_cold_cache_ready() -> None:
    """Test AgentColdStartDiagnostic when cache is cold (0 warm units) but other components are ready."""
    diagnostic = AgentColdStartDiagnostic()

    mock_configs = SimpleNamespace(model_cfg=SimpleNamespace(model="test-claude-3-5-sonnet"))

    mock_cache = MagicMock()
    mock_cache.warm_entry_count = 0

    with (
        patch("app.core.channel_bridge.config_loader.load_user_configs", AsyncMock(return_value=mock_configs)),
        patch("myrm_agent_harness.agent.tool_management.tool_layers.is_registered_action_tool", return_value=True),
        patch("app.services.agent.execution_cache.get_execution_cache", return_value=mock_cache),
        patch("app.database.connection.get_session") as mock_get_session,
    ):
        mock_session_ctx = MagicMock()
        mock_session = MagicMock()

        async def _fake_execute(*args, **kwargs):
            return 1

        mock_session.execute = _fake_execute
        mock_session_ctx.__aenter__.return_value = mock_session
        mock_session_ctx.__aexit__.return_value = None
        mock_get_session.return_value = mock_session_ctx

        report = await diagnostic.check_health()

        assert report.component_name == "AgentColdStart"
        assert report.status == "pass"
        assert report.code == "OK_AGENT_WARM_PATH_COLD_READY"
        assert report.meta_data is not None
        assert report.meta_data["warm_path_score"] == 90
        assert "model_ready" in report.meta_data["ready_phases"]
        assert "cache_warm" not in report.meta_data["ready_phases"]


@pytest.mark.asyncio
async def test_agent_cold_start_diagnostic_unconfigured_model() -> None:
    """Test AgentColdStartDiagnostic when no LLM is configured."""
    diagnostic = AgentColdStartDiagnostic()

    mock_configs = SimpleNamespace(model_cfg=SimpleNamespace(model=""))

    with (
        patch("app.core.channel_bridge.config_loader.load_user_configs", AsyncMock(return_value=mock_configs)),
        patch("myrm_agent_harness.agent.tool_management.tool_layers.is_registered_action_tool", return_value=True),
        patch("app.services.agent.execution_cache.get_execution_cache", side_effect=Exception("no cache")),
        patch("app.database.connection.get_session") as mock_get_session,
    ):
        mock_session_ctx = MagicMock()
        mock_session = MagicMock()

        async def _fake_execute(*args, **kwargs):
            return 1

        mock_session.execute = _fake_execute
        mock_session_ctx.__aenter__.return_value = mock_session
        mock_session_ctx.__aexit__.return_value = None
        mock_get_session.return_value = mock_session_ctx

        report = await diagnostic.check_health()

        assert report.component_name == "AgentColdStart"
        assert report.status == "warn"
        assert report.code == "WARN_AGENT_MODEL_UNCONFIGURED"
        assert report.fix_suggestion is not None
        assert "Settings -> Models" in report.fix_suggestion


@pytest.mark.asyncio
async def test_agent_cold_start_diagnostic_storage_degraded() -> None:
    """Test AgentColdStartDiagnostic when storage ping fails."""
    diagnostic = AgentColdStartDiagnostic()

    mock_configs = SimpleNamespace(model_cfg=SimpleNamespace(model="test-gpt-4o"))

    with (
        patch("app.core.channel_bridge.config_loader.load_user_configs", AsyncMock(return_value=mock_configs)),
        patch("myrm_agent_harness.agent.tool_management.tool_layers.is_registered_action_tool", return_value=True),
        patch("app.database.connection.get_session", side_effect=Exception("DB locked")),
    ):
        report = await diagnostic.check_health()

        assert report.component_name == "AgentColdStart"
        assert report.status == "warn"
        assert report.code == "WARN_AGENT_STORAGE_UNHEALTHY"
        assert report.fix_suggestion is not None
        assert "file lock" in report.fix_suggestion


@pytest.mark.asyncio
async def test_server_diagnostics_manager_includes_cold_start() -> None:
    """Test ServerDiagnosticsManager aggregates AgentColdStart probe."""
    manager = ServerDiagnosticsManager()
    probe_names = [p.__class__.__name__ for p in manager._probes]
    assert "AgentColdStartDiagnostic" in probe_names
    assert "DLQDiagnostic" in probe_names
    assert "ExecutionCacheDiagnostic" in probe_names

    reports = await manager.run_all()
    component_names = [r.component_name for r in reports]
    assert "AgentColdStart" in component_names


@pytest.mark.asyncio
async def test_run_server_diagnostics_shortcut() -> None:
    """Test run_server_diagnostics function returns healthy reports."""
    reports = await run_server_diagnostics()
    assert len(reports) >= 3
    assert any(r.component_name == "AgentColdStart" for r in reports)
