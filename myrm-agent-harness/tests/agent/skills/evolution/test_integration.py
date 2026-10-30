from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from myrm_agent_harness.agent.hooks.registry import HookRegistry
from myrm_agent_harness.agent.hooks.types import HookEvent
from myrm_agent_harness.agent.skills.evolution.core.types import EvolutionType
from myrm_agent_harness.agent.skills.evolution.infra.integration import (
    EvolutionIntegration,
    enable_skill_evolution,
    get_global_evolution_integration,
    set_global_evolution_integration,
)


@pytest.fixture
def clean_integration():
    yield
    set_global_evolution_integration(None)


@pytest.mark.asyncio
async def test_register_hooks_wires_only_the_session_end_frustration_trigger(clean_integration):
    integration = EvolutionIntegration(db_path=":memory:", enable_background_queue=True)
    try:
        registry = HookRegistry()
        integration.register_hooks(registry)
        integration.register_hooks(registry)

        assert registry.total_count == 1
        assert len(registry.get(HookEvent.SESSION_END)) == 1
    finally:
        await integration.close()


@pytest.mark.asyncio
async def test_session_end_hook_queues_a_derived_evolution_for_user_frustration(clean_integration):
    integration = EvolutionIntegration(db_path=":memory:", enable_background_queue=True)
    try:
        integration.queue = MagicMock()
        integration.queue.enqueue = AsyncMock()
        integration.queue.stop = AsyncMock()

        registry = HookRegistry()
        integration.register_hooks(registry)
        handler = registry.get(HookEvent.SESSION_END)[0].fn

        await handler(
            HookEvent.SESSION_END,
            {
                "session_id": "session-123",
                "messages": [
                    {"role": "assistant", "content": "Here is a long explanation."},
                    {"role": "user", "content": "废话太多"},
                ],
            },
        )

        assert integration.queue.enqueue.await_count == 1
        request = integration.queue.enqueue.call_args[0][0]
        assert request.evolution_type == EvolutionType.DERIVED
        assert request.skill_id == "frustration_verbosity_session-"
        assert request.user_feedback == "废话太多"
    finally:
        await integration.close()


@pytest.mark.asyncio
async def test_session_end_hook_queues_nothing_without_a_frustration_signal(clean_integration):
    integration = EvolutionIntegration(db_path=":memory:", enable_background_queue=True)
    try:
        integration.queue = MagicMock()
        integration.queue.enqueue = AsyncMock()
        integration.queue.stop = AsyncMock()

        registry = HookRegistry()
        integration.register_hooks(registry)
        handler = registry.get(HookEvent.SESSION_END)[0].fn

        await handler(
            HookEvent.SESSION_END,
            {
                "session_id": "session-123",
                "messages": [
                    {"role": "user", "content": "Summarize the report."},
                    {"role": "assistant", "content": "Done."},
                ],
            },
        )

        integration.queue.enqueue.assert_not_awaited()
    finally:
        await integration.close()


@pytest.mark.asyncio
async def test_global_integration_setter_getter(clean_integration):
    integration = EvolutionIntegration(db_path=":memory:")
    try:
        set_global_evolution_integration(integration)
        assert get_global_evolution_integration() is integration
        set_global_evolution_integration(None)
        assert get_global_evolution_integration() is None
    finally:
        await integration.close()


@pytest.mark.asyncio
async def test_integration_initialization_with_llm(clean_integration):
    mock_llm = MagicMock()
    with patch("myrm_agent_harness.agent.skills.evolution.infra.integration.SkillEvolutionEngine"):
        integration = EvolutionIntegration(
            db_path=":memory:",
            llm=mock_llm,
            enable_background_queue=True,
            enable_tde=True,
            enable_tool_calling=True,
        )
        try:
            assert integration.engine is not None
            assert integration.queue is not None
        finally:
            await integration.close()


@pytest.mark.asyncio
async def test_evolve_skill(clean_integration):
    integration = EvolutionIntegration(db_path=":memory:")
    try:
        integration.engine = MagicMock()
        integration.engine.fix_skill = AsyncMock(return_value=MagicMock())

        result = await integration.evolve_skill("test_skill", EvolutionType.FIX, reason="error")
        assert result is not None
        integration.engine.fix_skill.assert_called_once()
    finally:
        await integration.close()


@pytest.mark.asyncio
async def test_start_background_queue(clean_integration):
    integration = EvolutionIntegration(db_path=":memory:", enable_background_queue=True)
    try:
        integration.queue = MagicMock()
        integration.queue.start = AsyncMock()
        integration.queue.stop = AsyncMock()
        integration.queue.set_evolution_handler = MagicMock()
        integration.engine = MagicMock()  # Queue won't start without engine

        await integration.start_background_queue()
        integration.queue.start.assert_called_once()
        integration.queue.set_evolution_handler.assert_called_once()
    finally:
        await integration.close()


@pytest.mark.asyncio
async def test_close(clean_integration):
    integration = EvolutionIntegration(db_path=":memory:", enable_background_queue=True)
    integration.queue = MagicMock()
    integration.queue.stop = AsyncMock()
    integration.store = MagicMock()
    integration.store.close = MagicMock()

    await integration.close()
    integration.queue.stop.assert_called_once()
    integration.store.close.assert_called_once()


@pytest.mark.asyncio
async def test_evolve_skill_screener_blocks(clean_integration):
    integration = EvolutionIntegration(db_path=":memory:")
    try:
        integration.engine = MagicMock()
        integration.screener = AsyncMock()

        mock_result = MagicMock()
        mock_result.allowed = False
        mock_result.reason = "blocked"
        integration.screener.screen_request.return_value = mock_result

        result = await integration.evolve_skill("test_skill", EvolutionType.FIX)
        assert result is None
        integration.screener.screen_request.assert_called_once()
    finally:
        await integration.close()


@pytest.mark.asyncio
async def test_enable_skill_evolution(clean_integration):
    with patch("myrm_agent_harness.agent.skills.evolution.infra.integration.SkillEvolutionEngine"):
        integration = enable_skill_evolution(db_path=":memory:", enable_background_queue=True)
        try:
            assert isinstance(integration, EvolutionIntegration)
            assert integration.queue is not None
        finally:
            await integration.close()
