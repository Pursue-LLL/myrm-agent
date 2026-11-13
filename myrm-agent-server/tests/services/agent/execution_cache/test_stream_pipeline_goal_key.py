"""The pooled stream pipeline keys its execution-unit acquire by the goal state of the chat."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.ai_agents.general_agent.agent import GeneralAgent
from app.core.types import ModelConfig
from app.services.agent.execution_cache import (
    BuiltExecutionUnit,
    ExecutionMode,
    compute_execution_fingerprint,
    finalize_agent_session,
    get_execution_cache,
)
from app.services.agent.execution_cache.prewarm.coordinator import TurnPrewarmCoordinator
from app.services.agent.execution_cache.registry import BuildUnitFn
from app.services.agent.goals.goal_registry import GoalRegistry
from tests.support.pooled_pipeline import collect_pipeline_events, skill_agent_mock, stubbed_pipeline_edges


@pytest.fixture(autouse=True)
async def _reset_execution_cache_singleton() -> None:
    await get_execution_cache().close_all()
    yield
    await get_execution_cache().close_all()


@pytest.fixture(autouse=True)
def _mock_security_store_sync() -> None:
    with patch(
        "app.ai_agents.extensions.security_policy_extension.sync_wrapper_security_from_store",
        new=AsyncMock(),
    ):
        yield


@pytest.mark.asyncio
async def test_pooled_acquire_key_follows_the_goal_state_of_the_chat() -> None:
    """An active goal mounts complete_goal_tool and planning at build time, so the pipeline asks for
    the unit under the same key as the prewarm join: one that carries the goal state, replacing the
    idle unit that served the chat before."""
    chat_id = "chat-pool-goal"
    wrapper = GeneralAgent(
        model_cfg=ModelConfig(model="test-model", api_key="test-key", base_url="http://test"),
        mcp_config=None,
        chat_id=chat_id,
        agent_id="agent-goal",
    )
    idle_key = compute_execution_fingerprint(wrapper)
    goal_key = compute_execution_fingerprint(wrapper, has_active_goal=True)
    acquire_keys: list[str] = []
    coalesced_acquire = TurnPrewarmCoordinator.coalesced_acquire
    skill_agent = skill_agent_mock()

    async def recording_acquire(
        coordinator: TurnPrewarmCoordinator,
        scope_key: str,
        fingerprint: str,
        build_unit: BuildUnitFn,
        *,
        holds_turn_guard: bool = False,
    ) -> BuiltExecutionUnit:
        acquire_keys.append(fingerprint)
        return await coalesced_acquire(
            coordinator,
            scope_key,
            fingerprint,
            build_unit,
            holds_turn_guard=holds_turn_guard,
        )

    async def fake_run(
        *_args: object,
        **_kwargs: object,
    ) -> AsyncGenerator[dict[str, object], None]:
        yield {"type": "message", "data": "ok"}

    skill_agent.run = fake_run

    build_count = 0

    async def fake_build(
        agent_wrapper: GeneralAgent,
        effective_chat_id: str,
        user_id: str | None = None,
    ) -> MagicMock:
        nonlocal build_count
        build_count += 1
        agent_wrapper.agent = skill_agent
        return skill_agent

    async def send(query: str) -> None:
        await collect_pipeline_events(wrapper, chat_id=chat_id, query=query)
        await finalize_agent_session(
            wrapper,
            chat_id=chat_id,
            agent_id="agent-goal",
            extra_context={"execution_mode": ExecutionMode.POOLED},
        )

    with (
        patch("app.ai_agents.general_agent.factory.build_general_agent", side_effect=fake_build),
        patch.object(TurnPrewarmCoordinator, "coalesced_acquire", recording_acquire),
        stubbed_pipeline_edges(session_id="sess-goal"),
    ):
        await send("first")
        try:
            await GoalRegistry.get_or_create_provider(chat_id).create_goal(
                session_id=chat_id,
                objective="ship the weekly report",
            )
            await send("second")
        finally:
            GoalRegistry.unregister(chat_id)

    assert acquire_keys == [idle_key, goal_key]
    # The turn runs inside the scope's turn guard, yet its own acquire still swaps the idle unit for the goal one.
    assert build_count == 2
