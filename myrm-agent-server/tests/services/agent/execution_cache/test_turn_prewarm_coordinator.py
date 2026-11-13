"""Tests for TurnPrewarmCoordinator."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.ai_agents.general_agent.agent import GeneralAgent
from app.core.types import ModelConfig
from app.services.agent.execution_cache.fingerprint import compute_execution_fingerprint
from app.services.agent.execution_cache.prewarm.coordinator import TurnPrewarmCoordinator
from app.services.agent.execution_cache.registry import get_execution_cache
from app.services.agent.execution_cache.types import BuiltExecutionUnit
from app.services.agent.goals.goal_registry import GoalRegistry


@pytest.fixture(autouse=True)
async def _reset_execution_cache_singleton() -> None:
    await get_execution_cache().close_all()
    yield
    await get_execution_cache().close_all()


def _make_unit() -> BuiltExecutionUnit:
    skill_agent = MagicMock()
    skill_agent.close = AsyncMock()
    return BuiltExecutionUnit(skill_agent=skill_agent)


def _make_params(*, chat_id: str = "c-test", agent_id: str | None = "default") -> MagicMock:
    params = MagicMock()
    params.chat_id = chat_id
    params.agent_id = agent_id
    params.incognito_mode = False
    params.enable_memory = True
    params.embedding_config = object()
    return params


@pytest.mark.asyncio
async def test_coalesced_acquire_deduplicates_parallel_builds() -> None:
    coordinator = TurnPrewarmCoordinator()
    scope_key = "c-test:default"
    fingerprint = "fp-a"
    build_count = 0
    started = asyncio.Event()

    async def build_unit() -> BuiltExecutionUnit:
        nonlocal build_count
        build_count += 1
        started.set()
        await asyncio.sleep(0.05)
        return _make_unit()

    task_a = asyncio.create_task(
        coordinator.coalesced_acquire(scope_key, fingerprint, build_unit),
    )
    task_b = asyncio.create_task(
        coordinator.coalesced_acquire(scope_key, fingerprint, build_unit),
    )
    first, second = await asyncio.gather(task_a, task_b)

    assert first is second
    assert build_count == 1
    assert await get_execution_cache().is_warm(scope_key, fingerprint)


@pytest.mark.asyncio
async def test_join_for_turn_uses_brief_cache_when_ready() -> None:
    coordinator = TurnPrewarmCoordinator()
    scope_key = "c-test:default"
    fingerprint = "fp-b"
    preview = {"snapshot_id": "snap-1", "items": []}
    snapshot = {"snapshot_id": "snap-1"}
    coordinator._brief_cache.put(scope_key, fingerprint, preview, snapshot)

    params = _make_params()
    wrapper = MagicMock()
    wrapper.agent_id = "default"

    with (
        patch(
            "app.services.agent.execution_cache.prewarm.coordinator.AgentFactory.create_general_agent",
            return_value=wrapper,
        ),
        patch(
            "app.services.agent.execution_cache.prewarm.coordinator.compute_execution_fingerprint",
            return_value=fingerprint,
        ),
        patch(
            "app.services.agent.execution_cache.prewarm.coordinator.build_execution_scope_key",
            return_value=scope_key,
        ),
        patch.object(
            coordinator,
            "_should_warm_agent",
            return_value=False,
        ),
    ):
        result = await coordinator.join_for_turn(params)

    assert result.preview == preview
    assert result.snapshot == snapshot
    assert result.brief_status == {"state": "ready", "source": "preflight"}


@pytest.mark.asyncio
async def test_cancel_scope_clears_inflight_and_brief_cache() -> None:
    coordinator = TurnPrewarmCoordinator()
    scope_key = "c-test:default"
    fingerprint = "fp-c"
    coordinator._brief_cache.put(scope_key, fingerprint, {"snapshot_id": "x"}, {"snapshot_id": "x"})

    async def slow_build() -> BuiltExecutionUnit:
        await asyncio.sleep(5)
        return _make_unit()

    task = asyncio.create_task(
        coordinator.coalesced_acquire(scope_key, fingerprint, slow_build),
    )
    await asyncio.sleep(0.01)
    await coordinator.cancel_scope("c-test", "default")
    assert coordinator._brief_cache.get(scope_key, fingerprint) is None
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_cancel_scope_clears_agent_ready_timestamp() -> None:
    coordinator = TurnPrewarmCoordinator()
    coordinator._agent_ready_at["c-test:default:fp-c"] = 1.0

    await coordinator.cancel_scope("c-test", "default")

    assert coordinator._agent_ready_at == {}


def test_prune_agent_ready_timestamps_removes_expired_entries() -> None:
    coordinator = TurnPrewarmCoordinator()
    coordinator._agent_ready_at["expired"] = 1.0
    coordinator._brief_cache.put("c-expired:default", "fp", {}, {})
    coordinator._brief_cache._ttl_seconds = 0.0

    coordinator._prune_agent_ready_at()

    assert coordinator._agent_ready_at == {}
    assert coordinator._brief_cache.get("c-expired:default", "fp") is None


@pytest.mark.asyncio
@pytest.mark.parametrize(("enable_memory", "expected_warms"), [(True, 1), (False, 0)])
async def test_brief_is_prewarmed_for_memory_turns_without_an_embedding(enable_memory: bool, expected_warms: int) -> None:
    """Keyword mode (no embedding) builds the same memory brief, so it is warmed like any other memory turn."""
    coordinator = TurnPrewarmCoordinator()
    params = _make_params()
    params.enable_memory = enable_memory
    params.embedding_config = None

    with (
        patch("app.services.agent.execution_cache.prewarm.coordinator.AgentFactory.create_general_agent"),
        patch(
            "app.services.agent.execution_cache.prewarm.coordinator.compute_execution_fingerprint",
            return_value="fp",
        ),
        patch.object(coordinator, "_should_warm_agent", return_value=False),
        patch.object(coordinator, "_schedule_brief_warm", new=AsyncMock()) as schedule_brief,
    ):
        await coordinator.ensure_warming(params)

    assert schedule_brief.await_count == expected_warms


async def _leave_chat_with_active_goal(chat_id: str) -> None:
    """Persist an ACTIVE goal and drop the provider, as the end of a turn leaves a chat that has a goal."""
    await GoalRegistry.get_or_create_provider(chat_id).create_goal(
        session_id=chat_id,
        objective="ship the weekly report",
    )
    GoalRegistry.unregister(chat_id)


@pytest.mark.asyncio
@pytest.mark.parametrize(("with_goal", "expected_builds"), [(True, 0), (False, 1)])
async def test_ensure_warming_leaves_agent_build_to_the_turn_while_a_goal_is_active(
    with_goal: bool,
    expected_builds: int,
) -> None:
    """Between turns no goal provider is registered, so an agent built now would lack complete_goal_tool
    and the next turn would reuse it under the same key."""
    chat_id = f"c-goal-idle-{with_goal}"
    if with_goal:
        await _leave_chat_with_active_goal(chat_id)
    coordinator = TurnPrewarmCoordinator()

    with (
        patch("app.services.agent.execution_cache.prewarm.coordinator.AgentFactory.create_general_agent"),
        patch(
            "app.services.agent.execution_cache.prewarm.coordinator.compute_execution_fingerprint",
            return_value="fp",
        ),
        patch.object(coordinator, "_should_warm_agent", return_value=True),
        patch.object(coordinator, "_schedule_agent_warm", new=AsyncMock()) as schedule_agent,
        patch.object(coordinator, "_schedule_brief_warm", new=AsyncMock()),
    ):
        await coordinator.ensure_warming(_make_params(chat_id=chat_id))

    assert schedule_agent.await_count == expected_builds


async def _wait_until_warm(scope_key: str, fingerprint: str) -> None:
    async with asyncio.timeout(2):
        while not await get_execution_cache().is_warm(scope_key, fingerprint):
            await asyncio.sleep(0.01)


@pytest.mark.asyncio
async def test_join_for_turn_rebuilds_the_agent_when_a_goal_starts_between_turns() -> None:
    """The goal tools are mounted when the agent is built, so the turn that starts a goal must run
    on an agent built under it, not on the one that served the chat before."""
    chat_id = "c-goal-start"
    scope_key = f"{chat_id}:default"
    wrapper = GeneralAgent(
        model_cfg=ModelConfig(model="test-model", api_key="test-key", base_url="http://test"),
        mcp_config=None,
        chat_id=chat_id,
    )
    idle_key = compute_execution_fingerprint(wrapper)
    goal_key = compute_execution_fingerprint(wrapper, has_active_goal=True)
    params = _make_params(chat_id=chat_id)
    params.enable_memory = False
    coordinator = TurnPrewarmCoordinator()
    build_count = 0

    async def fake_build(
        agent_wrapper: GeneralAgent,
        effective_chat_id: str,
        user_id: str | None = None,
    ) -> MagicMock:
        nonlocal build_count
        build_count += 1
        skill_agent = MagicMock()
        skill_agent.close = AsyncMock()
        return skill_agent

    with (
        patch(
            "app.services.agent.execution_cache.prewarm.coordinator.AgentFactory.create_general_agent",
            return_value=wrapper,
        ),
        patch("app.ai_agents.general_agent.factory.build_general_agent", side_effect=fake_build),
    ):
        await coordinator.join_for_turn(params)
        await _wait_until_warm(scope_key, idle_key)
        await _leave_chat_with_active_goal(chat_id)
        await coordinator.join_for_turn(params)
        await _wait_until_warm(scope_key, goal_key)

    assert build_count == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("entry_point", ["ensure_warming", "join_for_turn"])
async def test_prewarm_keys_the_agent_by_goal_state(entry_point: str) -> None:
    """The goal is read from storage, not from the provider registry, so the key is the same
    whether or not a turn is running."""
    chat_id = f"c-goal-key-{entry_point}"
    await _leave_chat_with_active_goal(chat_id)
    coordinator = TurnPrewarmCoordinator()

    with (
        patch("app.services.agent.execution_cache.prewarm.coordinator.AgentFactory.create_general_agent"),
        patch(
            "app.services.agent.execution_cache.prewarm.coordinator.compute_execution_fingerprint",
            return_value="fp",
        ) as fingerprint,
        patch.object(coordinator, "_should_warm_agent", return_value=False),
        patch.object(coordinator, "_schedule_brief_warm", new=AsyncMock()),
    ):
        await getattr(coordinator, entry_point)(_make_params(chat_id=chat_id))

    assert fingerprint.call_args.kwargs == {"has_active_goal": True}


async def _build_while_holding_registry_lock(entered: asyncio.Event, finish: asyncio.Event) -> BuiltExecutionUnit:
    entered.set()
    await finish.wait()
    return _make_unit()


@pytest.mark.asyncio
async def test_guard_holder_finishes_the_replacement_a_prewarm_deferred() -> None:
    """A prewarm acquires without the turn guard, so once the turn holds it that acquire is deferred to the
    unit being replaced. The turn that joined it must still end on a unit of its own fingerprint."""
    coordinator = TurnPrewarmCoordinator()
    cache = get_execution_cache()
    scope_key = "c-holder-join:default"
    old_unit, new_unit = _make_unit(), _make_unit()
    await cache.acquire(scope_key, "fp-a", AsyncMock(return_value=old_unit))

    # Another chat's build holds the registry lock, so the prewarm and the turn queue behind it in this order.
    build_entered, finish_build = asyncio.Event(), asyncio.Event()
    other_chat_build = asyncio.create_task(
        cache.acquire("c-other:default", "fp-x", lambda: _build_while_holding_registry_lock(build_entered, finish_build))
    )
    await build_entered.wait()
    prewarm = asyncio.create_task(coordinator.coalesced_acquire(scope_key, "fp-b", AsyncMock(return_value=new_unit)))
    await asyncio.sleep(0.01)

    async with cache.guard_turn(scope_key):
        turn = asyncio.create_task(
            coordinator.coalesced_acquire(scope_key, "fp-b", AsyncMock(return_value=new_unit), holds_turn_guard=True)
        )
        await asyncio.sleep(0.01)
        finish_build.set()
        turn_unit = await turn

    assert await prewarm is old_unit
    assert turn_unit is new_unit
    assert await cache.is_warm(scope_key, "fp-b")
    old_unit.skill_agent.close.assert_awaited_once()
    await other_chat_build


@pytest.mark.asyncio
@pytest.mark.parametrize("prewarmed", [True, False])
async def test_guard_holder_builds_at_most_once(prewarmed: bool) -> None:
    """Checking the outcome of the acquire never costs a second build."""
    coordinator = TurnPrewarmCoordinator()
    scope_key = f"c-holder-once-{prewarmed}:default"
    prewarmed_unit = _make_unit()
    if prewarmed:
        await coordinator.coalesced_acquire(scope_key, "fp-a", AsyncMock(return_value=prewarmed_unit))
    own_unit = _make_unit()
    build = AsyncMock(return_value=own_unit)

    async with get_execution_cache().guard_turn(scope_key):
        unit = await coordinator.coalesced_acquire(scope_key, "fp-a", build, holds_turn_guard=True)

    assert unit is (prewarmed_unit if prewarmed else own_unit)
    assert build.await_count == (0 if prewarmed else 1)
