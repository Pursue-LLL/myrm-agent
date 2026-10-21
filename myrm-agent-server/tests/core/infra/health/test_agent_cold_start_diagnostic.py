"""Unit tests for Server business diagnostic probes, including AgentColdStartDiagnostic."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.infra.health.server_diagnostics import (
    AgentColdStartDiagnostic,
    ServerDiagnosticsManager,
    run_server_diagnostics,
)
from tests.support.minimal_app import build_minimal_app


@pytest.mark.asyncio
async def test_agent_cold_start_diagnostic_fully_ready() -> None:
    """Test AgentColdStartDiagnostic when all phases are primed and available."""
    diagnostic = AgentColdStartDiagnostic()

    mock_configs = SimpleNamespace(model_cfg=SimpleNamespace(model="test-gpt-4o"))

    mock_cache = MagicMock()
    mock_cache.warm_entry_count = 2

    with (
        patch(
            "app.core.channel_bridge.config_loader.load_user_configs",
            AsyncMock(return_value=mock_configs),
        ),
        patch("myrm_agent_harness.api.is_registered_action_tool", return_value=True),
        patch(
            "app.services.agent.execution_cache.get_execution_cache",
            return_value=mock_cache,
        ),
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
        ready_phases = list(report.meta_data.get("ready_phases", []))  # type: ignore[arg-type]
        assert "model_ready" in ready_phases
        assert "tools_ready" in ready_phases
        assert "cache_warm" in ready_phases
        assert "storage_healthy" in ready_phases
        assert report.fix_suggestion is None


@pytest.mark.asyncio
async def test_agent_cold_start_diagnostic_cold_cache_ready() -> None:
    """Test AgentColdStartDiagnostic when cache is cold (0 warm units) but other components are ready."""
    diagnostic = AgentColdStartDiagnostic()

    mock_configs = SimpleNamespace(model_cfg=SimpleNamespace(model="test-claude-3-5-sonnet"))

    mock_cache = MagicMock()
    mock_cache.warm_entry_count = 0

    with (
        patch(
            "app.core.channel_bridge.config_loader.load_user_configs",
            AsyncMock(return_value=mock_configs),
        ),
        patch("myrm_agent_harness.api.is_registered_action_tool", return_value=True),
        patch(
            "app.services.agent.execution_cache.get_execution_cache",
            return_value=mock_cache,
        ),
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
        ready_phases = list(report.meta_data.get("ready_phases", []))  # type: ignore[arg-type]
        assert "model_ready" in ready_phases
        assert "cache_warm" not in ready_phases


@pytest.mark.asyncio
async def test_agent_cold_start_diagnostic_unconfigured_model() -> None:
    """Test AgentColdStartDiagnostic when no LLM is configured."""
    diagnostic = AgentColdStartDiagnostic()

    mock_configs = SimpleNamespace(model_cfg=SimpleNamespace(model=""))

    with (
        patch(
            "app.core.channel_bridge.config_loader.load_user_configs",
            AsyncMock(return_value=mock_configs),
        ),
        patch("myrm_agent_harness.api.is_registered_action_tool", return_value=True),
        patch(
            "app.services.agent.execution_cache.get_execution_cache",
            side_effect=Exception("no cache"),
        ),
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
        patch(
            "app.core.channel_bridge.config_loader.load_user_configs",
            AsyncMock(return_value=mock_configs),
        ),
        patch("myrm_agent_harness.api.is_registered_action_tool", return_value=True),
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


@pytest.mark.asyncio
async def test_dlq_diagnostic_healthy_and_pending_redelivery() -> None:
    """Test DLQDiagnostic when DLQ is clean and pending outbound deliveries exist."""
    from app.core.infra.health.server_diagnostics import DLQDiagnostic

    diagnostic = DLQDiagnostic()

    mock_bus = MagicMock()
    mock_bus._dlq = MagicMock()
    mock_bus._dlq.get_failed_count = AsyncMock(return_value=0)
    mock_bus.durable_outbound = MagicMock()
    mock_bus.durable_outbound.count_pending = AsyncMock(return_value=3)

    mock_gateway = MagicMock()
    mock_gateway.bus = mock_bus

    with patch("app.core.channel_bridge.get_channel_gateway", return_value=mock_gateway):
        report = await diagnostic.check_health()
        assert report.component_name == "DLQ"
        assert report.status == "pass"
        assert report.code == "OK_DLQ_HEALTHY"
        assert report.meta_data is not None
        assert report.meta_data["failed_count"] == 0
        assert report.meta_data["pending_outbound_count"] == 3
        assert "3 pending outbound redelivery" in (report.detail or "")


@pytest.mark.asyncio
async def test_dlq_diagnostic_pending_backlog_warning() -> None:
    """Test DLQDiagnostic when pending outbound delivery count exceeds backlog threshold."""
    from app.core.infra.health.server_diagnostics import DLQDiagnostic

    diagnostic = DLQDiagnostic()

    mock_bus = MagicMock()
    mock_bus._dlq = MagicMock()
    mock_bus._dlq.get_failed_count = AsyncMock(return_value=2)
    mock_bus.durable_outbound = MagicMock()
    mock_bus.durable_outbound.count_pending = AsyncMock(return_value=60)

    mock_gateway = MagicMock()
    mock_gateway.bus = mock_bus

    with patch("app.core.channel_bridge.get_channel_gateway", return_value=mock_gateway):
        report = await diagnostic.check_health()
        assert report.component_name == "DLQ"
        assert report.status == "warn"
        assert report.code == "WARN_OUTBOUND_PENDING_BACKLOG"
        assert report.meta_data is not None
        assert report.meta_data["pending_outbound_count"] == 60
        assert report.fix_suggestion is not None


@pytest.mark.asyncio
async def test_dlq_diagnostic_critical_failures() -> None:
    """Test DLQDiagnostic when failed count exceeds critical threshold."""
    from app.core.infra.health.server_diagnostics import DLQDiagnostic

    diagnostic = DLQDiagnostic()

    mock_bus = MagicMock()
    mock_bus._dlq = MagicMock()
    mock_bus._dlq.get_failed_count = AsyncMock(return_value=120)
    mock_bus.durable_outbound = MagicMock()
    mock_bus.durable_outbound.count_pending = AsyncMock(return_value=0)

    mock_gateway = MagicMock()
    mock_gateway.bus = mock_bus

    with patch("app.core.channel_bridge.get_channel_gateway", return_value=mock_gateway):
        report = await diagnostic.check_health()
        assert report.component_name == "DLQ"
        assert report.status == "fail"
        assert report.code == "ERR_DLQ_CRITICAL"
        assert report.meta_data is not None
        assert report.meta_data["failed_count"] == 120
        assert report.fix_suggestion is not None


@pytest.mark.asyncio
async def test_doctor_api_endpoint_integrates_cold_start() -> None:
    """Test GET /api/v1/health/doctor endpoint returns AgentColdStart report."""
    app = build_minimal_app(preset="health")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/health/doctor")
        assert response.status_code == 200
        data = response.json()
        assert "server" in data
        assert "harness" in data
        assert "repair_actions" in data

        server_components = [item["component_name"] for item in data["server"]]
        assert "AgentColdStart" in server_components
        assert "ExecutionCache" in server_components
        assert "DLQ" in server_components
        assert "OllamaContext" in server_components
        assert "AgentStepBudget" in server_components
        assert "AgentPromptCacheAlignment" in server_components

        harness_components = [item["component_name"] for item in data["harness"]]
        assert len(harness_components) > 0


@pytest.mark.asyncio
async def test_ollama_model_context_diagnostic() -> None:
    """Test OllamaModelContextDiagnostic probe under various states."""
    import httpx

    from app.config.deploy_mode import DeployMode
    from app.core.infra.health.server_diagnostics import OllamaModelContextDiagnostic

    diagnostic = OllamaModelContextDiagnostic()

    # 1. Local mode with Ollama running and models available
    with patch("app.config.deploy_mode.get_deploy_mode", return_value=DeployMode.LOCAL):
        with patch("httpx.AsyncClient.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {
                "models": [
                    {"name": "qwen2.5:14b"},
                    {"name": "qwen2.5:14b-agentic"},
                ]
            }
            mock_get.return_value = mock_resp

            report = await diagnostic.check_health()
            assert report.component_name == "OllamaContext"
            assert report.status == "pass"
            assert report.code == "OK_OLLAMA_CONTEXT_READY"
            assert report.meta_data["total_models"] == 2
            assert "qwen2.5:14b-agentic" in report.meta_data["agentic_models"]

    # 2. Local mode with Ollama running but NO agentic models created yet
    with patch("app.config.deploy_mode.get_deploy_mode", return_value=DeployMode.LOCAL):
        with patch("httpx.AsyncClient.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {
                "models": [
                    {"name": "qwen2.5:14b"},
                ]
            }
            mock_get.return_value = mock_resp

            report = await diagnostic.check_health()
            assert report.component_name == "OllamaContext"
            assert report.status == "warn"
            assert report.code == "WARN_OLLAMA_NO_AGENTIC_MODELS"
            assert report.fix_suggestion is not None

    # 3. Sandbox mode skips Ollama probe
    with patch("app.config.deploy_mode.get_deploy_mode", return_value=DeployMode.SANDBOX):
        report = await diagnostic.check_health()
        assert report.component_name == "OllamaContext"
        assert report.status == "pass"
        assert report.code == "OK_OLLAMA_SANDBOX_SKIPPED"

    # 4. Local mode with Ollama unreachable (e.g. connection refused)
    with patch("app.config.deploy_mode.get_deploy_mode", return_value=DeployMode.LOCAL):
        with patch(
            "httpx.AsyncClient.get",
            side_effect=httpx.ConnectError("Connection refused"),
        ):
            report = await diagnostic.check_health()
            assert report.component_name == "OllamaContext"
            assert report.status == "pass"
            assert report.code == "INFO_OLLAMA_UNREACHABLE"


@pytest.mark.asyncio
async def test_agent_step_budget_diagnostic() -> None:
    """Test AgentStepBudgetDiagnostic probe for normal and low-budget agents."""
    from app.core.infra.health.server_diagnostics import AgentStepBudgetDiagnostic

    diagnostic = AgentStepBudgetDiagnostic()

    # 1. When all agents have >= 100 max_iterations (or None/unlimited)
    agent_ok_1 = SimpleNamespace(id="ag_1", name="Research Agent", max_iterations=100, is_active=True)
    agent_ok_2 = SimpleNamespace(id="ag_2", name="Code Agent", max_iterations=None, is_active=True)

    with patch("app.database.connection.get_session") as mock_get_session:
        mock_session_ctx = MagicMock()
        mock_session = MagicMock()

        mock_res = MagicMock()
        mock_res.scalars.return_value.all.return_value = [agent_ok_1, agent_ok_2]

        async def _fake_execute(*args, **kwargs):
            return mock_res

        mock_session.execute = _fake_execute
        mock_session_ctx.__aenter__.return_value = mock_session
        mock_session_ctx.__aexit__.return_value = None
        mock_get_session.return_value = mock_session_ctx

        report = await diagnostic.check_health()
        assert report.component_name == "AgentStepBudget"
        assert report.status == "pass"
        assert report.code == "OK_AGENT_STEP_BUDGET_READY"
        assert report.metrics["low_budget_agent_count"] == 0.0
        assert report.metrics["total_active_agents"] == 2.0

    # 2. When an agent has low step budget (< 100, e.g., 30 steps)
    agent_low = SimpleNamespace(id="ag_low", name="Legacy Agent", max_iterations=30, is_active=True)

    with patch("app.database.connection.get_session") as mock_get_session:
        mock_session_ctx = MagicMock()
        mock_session = MagicMock()

        mock_res = MagicMock()
        mock_res.scalars.return_value.all.return_value = [agent_ok_1, agent_low]

        async def _fake_execute(*args, **kwargs):
            return mock_res

        mock_session.execute = _fake_execute
        mock_session_ctx.__aenter__.return_value = mock_session
        mock_session_ctx.__aexit__.return_value = None
        mock_get_session.return_value = mock_session_ctx

        report = await diagnostic.check_health()
        assert report.component_name == "AgentStepBudget"
        assert report.status == "warn"
        assert report.code == "WARN_AGENT_STEP_BUDGET_LOW"
        assert report.metrics["low_budget_agent_count"] == 1.0
        assert report.fix_suggestion is not None
        assert "Legacy Agent" in report.detail

    # 3. When an agent has low step budget but is an exempt lightweight mode (e.g. search mode)
    agent_search = SimpleNamespace(
        id="ag_search",
        name="Fast Search Agent",
        max_iterations=30,
        prompt_mode="search",
        is_active=True,
    )

    with patch("app.database.connection.get_session") as mock_get_session:
        mock_session_ctx = MagicMock()
        mock_session = MagicMock()

        mock_res = MagicMock()
        mock_res.scalars.return_value.all.return_value = [agent_ok_1, agent_search]

        async def _fake_execute(*args, **kwargs):
            return mock_res

        mock_session.execute = _fake_execute
        mock_session_ctx.__aenter__.return_value = mock_session
        mock_session_ctx.__aexit__.return_value = None
        mock_get_session.return_value = mock_session_ctx

        report = await diagnostic.check_health()
        assert report.component_name == "AgentStepBudget"
        assert report.status == "pass"
        assert report.code == "OK_AGENT_STEP_BUDGET_READY"
        assert report.metrics["low_budget_agent_count"] == 0.0

    # 4. When database throws an exception (e.g., table not created yet)
    with patch(
        "app.database.connection.get_session",
        side_effect=RuntimeError("DB disconnected"),
    ):
        report = await diagnostic.check_health()
        assert report.component_name == "AgentStepBudget"
        assert report.status == "pass"
        assert report.code == "OK_AGENT_STEP_BUDGET_SKIPPED"


@pytest.mark.asyncio
async def test_agent_prompt_cache_alignment_diagnostic() -> None:
    """Test AgentPromptCacheAlignmentDiagnostic probe for static and jittery system prompts."""
    from app.core.infra.health.server_diagnostics import (
        AgentPromptCacheAlignmentDiagnostic,
    )

    diagnostic = AgentPromptCacheAlignmentDiagnostic()

    # 1. When all agents have static, cache-aligned system prompts
    agent_ok_1 = SimpleNamespace(
        id="ag_1",
        name="Static Prompt Agent",
        system_prompt="You are a senior software architect. Always adhere to clean code.",
        is_active=True,
    )
    agent_ok_2 = SimpleNamespace(
        id="ag_2",
        name="Empty Prompt Agent",
        system_prompt="",
        is_active=True,
    )

    with patch("app.database.connection.get_session") as mock_get_session:
        mock_session_ctx = MagicMock()
        mock_session = MagicMock()
        mock_res = MagicMock()
        mock_res.scalars.return_value.all.return_value = [agent_ok_1, agent_ok_2]

        async def _fake_execute(*args, **kwargs):
            return mock_res

        mock_session.execute = _fake_execute
        mock_session_ctx.__aenter__.return_value = mock_session
        mock_session_ctx.__aexit__.return_value = None
        mock_get_session.return_value = mock_session_ctx

        report = await diagnostic.check_health()
        assert report.component_name == "AgentPromptCacheAlignment"
        assert report.status == "pass"
        assert report.code == "OK_PROMPT_CACHE_ALIGNED"
        assert report.metrics["jitter_agent_count"] == 0.0
        assert report.metrics["total_active_agents"] == 2.0

    # 2. When an agent has dynamic timestamp placeholder in system prompt header (Jitter Anti-Pattern)
    agent_jitter = SimpleNamespace(
        id="ag_jitter",
        name="Jittery Agent",
        system_prompt="Current Time: {{current_time}}\nYou are a helpful AI assistant.",
        is_active=True,
    )

    with patch("app.database.connection.get_session") as mock_get_session:
        mock_session_ctx = MagicMock()
        mock_session = MagicMock()
        mock_res = MagicMock()
        mock_res.scalars.return_value.all.return_value = [agent_ok_1, agent_jitter]

        async def _fake_execute(*args, **kwargs):
            return mock_res

        mock_session.execute = _fake_execute
        mock_session_ctx.__aenter__.return_value = mock_session
        mock_session_ctx.__aexit__.return_value = None
        mock_get_session.return_value = mock_session_ctx

        report = await diagnostic.check_health()
        assert report.component_name == "AgentPromptCacheAlignment"
        assert report.status == "warn"
        assert report.code == "WARN_PROMPT_CACHE_PREFIX_JITTER"
        assert report.metrics["jitter_agent_count"] == 1.0
        assert "Jittery Agent" in report.detail
        assert report.fix_suggestion is not None

    # 3. When database throws an exception
    with patch(
        "app.database.connection.get_session",
        side_effect=RuntimeError("DB disconnected"),
    ):
        report = await diagnostic.check_health()
        assert report.component_name == "AgentPromptCacheAlignment"
        assert report.status == "pass"
        assert report.code == "OK_PROMPT_CACHE_ALIGNMENT_SKIPPED"
