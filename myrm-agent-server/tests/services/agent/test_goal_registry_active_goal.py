"""GoalRegistry.has_active_goal: the goal state that execution-cache keys depend on."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from myrm_agent_harness.agent.goals.types import GoalStatus

from app.services.agent.goals.goal_registry import GoalRegistry


@pytest.fixture
def chat_id(request: pytest.FixtureRequest) -> Iterator[str]:
    session_id = f"has-active-goal-{request.node.name}"
    yield session_id
    GoalRegistry.unregister(session_id)


@pytest.mark.asyncio
async def test_false_without_a_goal(chat_id: str) -> None:
    assert await GoalRegistry.has_active_goal(chat_id) is False


@pytest.mark.asyncio
async def test_true_for_an_active_goal(chat_id: str) -> None:
    await GoalRegistry.get_or_create_provider(chat_id).create_goal(session_id=chat_id, objective="ship the weekly report")

    assert await GoalRegistry.has_active_goal(chat_id) is True


@pytest.mark.asyncio
async def test_true_after_the_turn_unregisters_the_provider(chat_id: str) -> None:
    """The end of a turn drops the provider; the goal outlives it, and probing must not register one again."""
    await GoalRegistry.get_or_create_provider(chat_id).create_goal(session_id=chat_id, objective="ship the weekly report")
    GoalRegistry.unregister(chat_id)

    assert await GoalRegistry.has_active_goal(chat_id) is True
    assert GoalRegistry.get_provider(chat_id) is None


@pytest.mark.asyncio
async def test_false_once_the_goal_leaves_active(chat_id: str) -> None:
    provider = GoalRegistry.get_or_create_provider(chat_id)
    goal = await provider.create_goal(session_id=chat_id, objective="ship the weekly report")
    await provider.update_status(goal.goal_id, GoalStatus.PAUSED)

    assert await GoalRegistry.has_active_goal(chat_id) is False
