"""Failure isolation of goal queue chaining and the loop-restart callback."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.ai_agents.general_agent.goal_learnings import _try_dequeue_next, build_loop_restart_callback

_REGISTRY = "app.services.agent.goals.goal_registry.GoalRegistry"
_TRIGGER = "app.services.agent.goals.goal_stream_trigger.trigger_goal_stream_with_failure_policy"
_EVENT_BUS = "app.services.event.app_event_bus.get_event_bus"


def _queued_goal(goal_id: str) -> MagicMock:
    goal = MagicMock()
    goal.goal_id = goal_id
    goal.objective = f"objective of {goal_id}"
    return goal


def _registry_with(provider: AsyncMock) -> MagicMock:
    registry = MagicMock()
    registry.get_provider.return_value = provider
    return registry


@pytest.mark.asyncio
async def test_dequeue_failure_stops_the_chain_without_starting_a_stream() -> None:
    provider = AsyncMock()
    provider.dequeue_next.side_effect = RuntimeError("queue store unavailable")

    with patch(_REGISTRY, _registry_with(provider)), patch(_TRIGGER, new_callable=AsyncMock) as trigger:
        await _try_dequeue_next("session-1")

    trigger.assert_not_awaited()


@pytest.mark.asyncio
async def test_event_bus_failure_does_not_prevent_starting_the_next_goal() -> None:
    provider = AsyncMock()
    next_goal = _queued_goal("g-next")
    provider.dequeue_next.return_value = next_goal

    with (
        patch(_REGISTRY, _registry_with(provider)),
        patch(_EVENT_BUS, side_effect=RuntimeError("bus closed")),
        patch(_TRIGGER, new_callable=AsyncMock, return_value=True) as trigger,
    ):
        await _try_dequeue_next("session-1")

    trigger.assert_awaited_once()
    assert trigger.await_args.args[1] is next_goal


@pytest.mark.asyncio
async def test_failed_start_moves_on_to_the_following_queued_goal() -> None:
    provider = AsyncMock()
    first, second = _queued_goal("g-1"), _queued_goal("g-2")
    provider.dequeue_next.side_effect = [first, second, None]

    with (
        patch(_REGISTRY, _registry_with(provider)),
        patch(_EVENT_BUS, return_value=MagicMock()),
        patch(_TRIGGER, new_callable=AsyncMock, side_effect=[False, True]) as trigger,
    ):
        await _try_dequeue_next("session-1")

    assert [call.args[1] for call in trigger.await_args_list] == [first, second]


@pytest.mark.asyncio
async def test_loop_restart_retriggers_the_goal_and_keeps_it_active_on_failure() -> None:
    provider = AsyncMock()
    goal = _queued_goal("g-loop")
    goal.loop_restarts = 2

    with patch(_REGISTRY, _registry_with(provider)), patch(_TRIGGER, new_callable=AsyncMock) as trigger:
        await build_loop_restart_callback()("session-1", goal)

    trigger.assert_awaited_once_with(
        "session-1",
        goal,
        provider,
        on_failure="keep_active",
        context="loop restart",
    )
