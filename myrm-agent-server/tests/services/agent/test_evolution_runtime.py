"""Skill evolution runtime: startup prerequisites, proposal routing, shutdown."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from myrm_agent_harness.agent.event_log.backends.file_backend import FileEventLogBackend
from myrm_agent_harness.agent.event_log.logger import EventLogger
from myrm_agent_harness.agent.skills.evolution.infra.integration import set_global_evolution_integration
from myrm_agent_harness.agent.streaming.broadcast.tool_call_broadcaster import ToolCallBroadcaster

from app.services.agent.evolution import evolution_runtime


@pytest.fixture(autouse=True)
def _fresh_runtime() -> Iterator[None]:
    original = evolution_runtime._started_integration
    evolution_runtime._started_integration = None
    yield
    evolution_runtime._started_integration = original


@contextmanager
def _startup_environment(integration: MagicMock) -> Iterator[tuple[MagicMock, MagicMock]]:
    """Patch every startup dependency; yields (screener_cls, integration_factory)."""
    llm_manager = MagicMock()
    llm_manager.get_llm_from_config = AsyncMock(return_value=MagicMock())
    integration_factory = MagicMock(return_value=integration)
    with ExitStack() as stack:
        stack.enter_context(patch.object(evolution_runtime, "get_global_evolution_integration", return_value=None))
        stack.enter_context(patch.object(evolution_runtime, "llm_manager", llm_manager))
        stack.enter_context(
            patch.object(
                evolution_runtime,
                "load_platform_evolution_model_config",
                new=AsyncMock(return_value=SimpleNamespace()),
            )
        )
        screener_cls = stack.enter_context(patch.object(evolution_runtime, "EvolutionScreener"))
        stack.enter_context(patch.object(evolution_runtime, "EvolutionIntegration", integration_factory))
        yield screener_cls, integration_factory


@pytest.mark.asyncio
async def test_runtime_starts_with_evolution_model_only() -> None:
    integration = MagicMock()
    integration.start_background_queue = AsyncMock()
    embedding_requirement = AsyncMock(side_effect=RuntimeError("embedding must not be required"))

    with (
        patch("app.services.agent.platform_config.require_platform_embedding_config", new=embedding_requirement),
        _startup_environment(integration) as (screener_cls, integration_factory),
    ):
        await evolution_runtime.init_evolution_runtime()

    integration_factory.assert_called_once()
    assert "vector_store" not in integration_factory.call_args.kwargs
    assert "embedding" not in integration_factory.call_args.kwargs
    embedding_requirement.assert_not_awaited()
    assert screener_cls.call_args.kwargs["store"] is integration.store
    assert integration.screener is screener_cls.return_value
    integration.start_background_queue.assert_awaited_once_with(on_proposal_callback=evolution_runtime.handle_new_proposal)
    assert evolution_runtime._started_integration is integration


@pytest.mark.asyncio
async def test_the_engine_the_runtime_builds_reads_the_event_logs_the_agents_write(tmp_path: Path) -> None:
    state_dir = tmp_path / "state"
    log_dir = tmp_path / "event_logs"
    state_dir.mkdir()
    log_dir.mkdir()
    chat_id = "c-runtime-1"
    # What an agent run writes: the file is named by the chat id, the events carry the session key of the run.
    backend = FileEventLogBackend(log_dir, chat_id)
    event_logger = EventLogger(backend, f"chat_{chat_id}")
    await event_logger.start()
    broadcaster = ToolCallBroadcaster(event_logger)
    call = {"tool_name": "bash", "tool_call_id": "call-1", "session_id": f"chat_{chat_id}"}
    await broadcaster.on_pre_tool_use("pre_tool_use", {**call, "tool_input": {"command": "ls"}})
    await broadcaster.on_post_tool_use_failure("post_tool_use_failure", {**call, "error": "exit 1"})
    await event_logger.close()

    llm_manager = MagicMock()
    llm_manager.get_llm_from_config = AsyncMock(return_value=MagicMock())
    settings = SimpleNamespace(database=SimpleNamespace(state_dir=str(state_dir), event_log_dir=str(log_dir)))
    try:
        with (
            patch.object(evolution_runtime, "settings", settings),
            patch.object(evolution_runtime, "get_global_evolution_integration", return_value=None),
            patch.object(evolution_runtime, "llm_manager", llm_manager),
            patch.object(
                evolution_runtime, "load_platform_evolution_model_config", new=AsyncMock(return_value=SimpleNamespace())
            ),
        ):
            await evolution_runtime.init_evolution_runtime()

        integration = evolution_runtime._started_integration
        assert integration is not None
        assert integration.engine is not None
        trajectory = await integration.engine._trace_analyzer.extract_trajectory(chat_id, "bash")
    finally:
        await evolution_runtime.shutdown_evolution_runtime()
        set_global_evolution_integration(None)

    assert "[tool_failure]" in trajectory
    assert "exit 1" in trajectory


@pytest.mark.asyncio
async def test_runtime_is_disabled_without_evolution_model() -> None:
    integration_factory = MagicMock()

    with (
        patch.object(evolution_runtime, "get_global_evolution_integration", return_value=None),
        patch.object(
            evolution_runtime,
            "load_platform_evolution_model_config",
            new=AsyncMock(side_effect=RuntimeError("not configured")),
        ),
        patch.object(evolution_runtime, "EvolutionIntegration", integration_factory),
    ):
        await evolution_runtime.init_evolution_runtime()

    integration_factory.assert_not_called()
    assert evolution_runtime._started_integration is None


@pytest.mark.asyncio
async def test_runtime_leaves_an_existing_global_integration_alone() -> None:
    integration_factory = MagicMock()

    with (
        patch.object(evolution_runtime, "get_global_evolution_integration", return_value=MagicMock()),
        patch.object(evolution_runtime, "EvolutionIntegration", integration_factory),
    ):
        await evolution_runtime.init_evolution_runtime()

    integration_factory.assert_not_called()
    assert evolution_runtime._started_integration is None


@pytest.mark.asyncio
async def test_shutdown_stops_the_queue_it_started() -> None:
    integration = MagicMock()
    integration.stop_background_queue = AsyncMock()
    evolution_runtime._started_integration = integration

    await evolution_runtime.shutdown_evolution_runtime()

    integration.stop_background_queue.assert_awaited_once()
    assert evolution_runtime._started_integration is None


@pytest.mark.asyncio
async def test_shutdown_without_started_runtime_is_a_noop() -> None:
    await evolution_runtime.shutdown_evolution_runtime()

    assert evolution_runtime._started_integration is None


@pytest.mark.asyncio
async def test_proposal_is_persisted_through_the_approval_flow() -> None:
    proposal = MagicMock(skill_id="s1", score=0.9)
    flow = MagicMock()
    flow.process_evolution = AsyncMock(return_value=SimpleNamespace(approved=False))

    with patch.object(evolution_runtime, "ConfidenceApprovalFlow", MagicMock(return_value=flow)):
        await evolution_runtime.handle_new_proposal(proposal)

    flow.process_evolution.assert_awaited_once_with(proposal)


@pytest.mark.asyncio
async def test_persistence_failure_is_logged_and_contained() -> None:
    proposal = MagicMock(skill_id="s1", score=0.9)
    flow = MagicMock()
    flow.process_evolution = AsyncMock(side_effect=RuntimeError("db down"))

    with (
        patch.object(evolution_runtime, "ConfidenceApprovalFlow", MagicMock(return_value=flow)),
        patch.object(evolution_runtime, "logger") as logger,
    ):
        await evolution_runtime.handle_new_proposal(proposal)

    logger.error.assert_called_once()
