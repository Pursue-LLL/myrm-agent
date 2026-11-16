"""A rewind pauses the chat's active goal.

The rewind is refused while a turn runs, so it always arrives between turns, when the chat has no registered provider
and its goals are in storage.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from unittest.mock import patch

import pytest
from myrm_agent_harness.agent.goals.types import GoalStatus
from myrm_agent_harness.toolkits.storage.local import LocalStorageBackend

from app.services.agent.goals.goal_registry import GoalRegistry
from app.services.chat.session_continuity_service import pause_active_goal_for_rewind


@pytest.fixture(autouse=True)
def storage(tmp_path: Path) -> Iterator[None]:
    with patch("app.platform_utils.get_storage_provider", return_value=LocalStorageBackend(str(tmp_path))):
        yield


@pytest.fixture
def chat_id(request: pytest.FixtureRequest) -> Iterator[str]:
    session_id = f"rewind-goal-{request.node.name}"
    yield session_id
    GoalRegistry.unregister(session_id)


@pytest.mark.asyncio
async def test_an_active_goal_is_paused_with_the_rewind_as_the_reason(chat_id: str) -> None:
    goal = await GoalRegistry.resolve_provider(chat_id).create_goal(chat_id, "ship the weekly report")
    assert GoalRegistry.get_provider(chat_id) is None

    paused = await pause_active_goal_for_rewind(chat_id)

    assert paused is True
    stored = await GoalRegistry.resolve_provider(chat_id).get_goal(goal.goal_id)
    assert stored is not None
    assert stored.status is GoalStatus.PAUSED
    assert stored.metadata["pause_reason"] == "Conversation rewind requested"
    assert GoalRegistry.get_provider(chat_id) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [GoalStatus.PAUSED, GoalStatus.WAIT, GoalStatus.NEEDS_HUMAN_REVIEW])
async def test_a_goal_that_is_not_active_is_left_alone(chat_id: str, status: GoalStatus) -> None:
    provider = GoalRegistry.resolve_provider(chat_id)
    goal = await provider.create_goal(chat_id, "ship the weekly report")
    await provider.update_status(goal.goal_id, status)

    paused = await pause_active_goal_for_rewind(chat_id)

    assert paused is False
    stored = await provider.get_goal(goal.goal_id)
    assert stored is not None
    assert stored.status is status


@pytest.mark.asyncio
async def test_a_chat_without_a_goal_has_nothing_to_pause(chat_id: str) -> None:
    assert await pause_active_goal_for_rewind(chat_id) is False
