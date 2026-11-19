"""Goal queue chaining and the loop-restart callback: both start the goal's next turn once the last one has ended it.

The harness schedules these callbacks at the turn's last verdict, while that turn winds down: its provider may already be
given back. They therefore work from storage through the registry's stand-in, and a failure in one start does not stop
the chain.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from myrm_agent_harness.agent.goals.types import Goal, GoalStatus
from myrm_agent_harness.toolkits.storage.local import LocalStorageBackend

from app.ai_agents.general_agent.goal_learnings import _try_dequeue_next, build_loop_restart_callback
from app.services.agent.goals.goal_registry import GoalRegistry

_TRIGGER = "app.services.agent.goals.unattended.trigger_goal_stream_with_failure_policy"
_EVENT_BUS = "app.services.event.app_event_bus.get_event_bus"


@pytest.fixture(autouse=True)
def storage(tmp_path: Path) -> Iterator[None]:
    with patch("app.platform_utils.get_storage_provider", return_value=LocalStorageBackend(str(tmp_path))):
        yield


@pytest.fixture
def chat_id(request: pytest.FixtureRequest) -> str:
    return f"queue-callbacks-{request.node.name}"


async def _queue_behind_an_ended_goal(chat_id: str, *objectives: str) -> list[Goal]:
    """The chat's goal has just ended with ``objectives`` queued behind it; returns the queued goals in order."""
    provider = GoalRegistry.resolve_provider(chat_id)
    ended = await provider.create_goal(chat_id, "ended")
    queued = [await provider.create_goal(chat_id, objective) for objective in objectives]
    await provider.update_status(ended.goal_id, GoalStatus.CANCELLED)
    return queued


@pytest.mark.asyncio
async def test_the_next_queued_goal_starts_though_no_turn_is_running(chat_id: str) -> None:
    (second,) = await _queue_behind_an_ended_goal(chat_id, "second")

    with patch(_EVENT_BUS, return_value=MagicMock()), patch(_TRIGGER, new_callable=AsyncMock, return_value=True) as trigger:
        await _try_dequeue_next(chat_id)

    trigger.assert_awaited_once()
    session, goal = trigger.await_args.args
    assert (session, goal.goal_id) == (chat_id, second.goal_id)
    assert goal.status is GoalStatus.ACTIVE
    assert trigger.await_args.kwargs == {"context": "dequeued goal"}
    assert GoalRegistry.get_provider(chat_id) is None


@pytest.mark.asyncio
async def test_an_empty_queue_starts_nothing(chat_id: str) -> None:
    await _queue_behind_an_ended_goal(chat_id)

    with patch(_TRIGGER, new_callable=AsyncMock) as trigger:
        await _try_dequeue_next(chat_id)

    trigger.assert_not_awaited()


@pytest.mark.asyncio
async def test_the_chain_stops_at_the_depth_limit_and_leaves_the_queue_alone(chat_id: str) -> None:
    (second,) = await _queue_behind_an_ended_goal(chat_id, "second")

    with patch(_TRIGGER, new_callable=AsyncMock) as trigger:
        await _try_dequeue_next(chat_id, _depth=5)

    trigger.assert_not_awaited()
    still_queued = await GoalRegistry.resolve_provider(chat_id).get_goal(second.goal_id)
    assert still_queued is not None and still_queued.status is GoalStatus.QUEUED


@pytest.mark.asyncio
async def test_dequeue_failure_stops_the_chain_without_starting_a_stream(chat_id: str) -> None:
    await _queue_behind_an_ended_goal(chat_id, "second")

    with (
        patch(
            "app.services.agent.goals.goal_registry.ServerGoalManager.dequeue_next",
            new_callable=AsyncMock,
            side_effect=RuntimeError("queue store unavailable"),
        ),
        patch(_TRIGGER, new_callable=AsyncMock) as trigger,
    ):
        await _try_dequeue_next(chat_id)

    trigger.assert_not_awaited()


@pytest.mark.asyncio
async def test_event_bus_failure_does_not_prevent_starting_the_next_goal(chat_id: str) -> None:
    (second,) = await _queue_behind_an_ended_goal(chat_id, "second")

    with (
        patch(_EVENT_BUS, side_effect=RuntimeError("bus closed")),
        patch(_TRIGGER, new_callable=AsyncMock, return_value=True) as trigger,
    ):
        await _try_dequeue_next(chat_id)

    trigger.assert_awaited_once()
    assert trigger.await_args.args[1].goal_id == second.goal_id


@pytest.mark.asyncio
async def test_failed_start_moves_on_to_the_following_queued_goal(chat_id: str) -> None:
    first, second = await _queue_behind_an_ended_goal(chat_id, "first", "second")

    with (
        patch(_EVENT_BUS, return_value=MagicMock()),
        patch(_TRIGGER, new_callable=AsyncMock, side_effect=[False, True]) as trigger,
    ):
        await _try_dequeue_next(chat_id)

    assert [call.args[1].goal_id for call in trigger.await_args_list] == [first.goal_id, second.goal_id]


@pytest.mark.asyncio
async def test_loop_restart_retriggers_the_goal() -> None:
    goal = MagicMock()
    goal.goal_id = "g-loop"
    goal.objective = "objective of g-loop"
    goal.loop_restarts = 2

    with patch(_TRIGGER, new_callable=AsyncMock) as trigger:
        await build_loop_restart_callback()("session-1", goal)

    trigger.assert_awaited_once_with("session-1", goal, context="loop restart")
