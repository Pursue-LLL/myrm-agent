"""A goal pause or cancel is the user's stop for the chat's autonomous wakes, and a resume lifts it again."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from unittest.mock import MagicMock

import pytest
from myrm_agent_harness.agent.goals.types import GoalStatus

from app.services.agent.adaptive_wakeup import get_adaptive_wakeup_service
from app.services.agent.goals.goal_controls import note_goal_resumed, stop_goal_turn


@pytest.fixture
def session_id() -> Iterator[str]:
    session = f"goal-{uuid.uuid4().hex[:8]}"
    yield session
    get_adaptive_wakeup_service().forget_chat(session)


def goal_in(status: GoalStatus) -> MagicMock:
    goal = MagicMock()
    goal.status = status
    return goal


@pytest.mark.parametrize("status", [GoalStatus.ACTIVE, GoalStatus.WAIT, GoalStatus.NEEDS_HUMAN_REVIEW])
def test_pausing_or_cancelling_a_goal_holds_the_chats_wakes_whatever_state_it_was_in(session_id: str, status: GoalStatus) -> None:
    stop_goal_turn(session_id, goal_in(status))

    assert get_adaptive_wakeup_service().get_budget_state(session_id).is_user_stopped


def test_a_stop_of_one_chats_goal_leaves_the_wakes_of_other_chats_alone(session_id: str) -> None:
    other = f"other-{uuid.uuid4().hex[:8]}"

    stop_goal_turn(session_id, goal_in(GoalStatus.ACTIVE))

    assert not get_adaptive_wakeup_service().get_budget_state(other).is_user_stopped


def test_resuming_the_goal_lifts_the_hold_and_restores_the_budget(session_id: str) -> None:
    service = get_adaptive_wakeup_service()
    while service.router.claim_wake_turn(session_id):
        pass
    stop_goal_turn(session_id, goal_in(GoalStatus.ACTIVE))

    note_goal_resumed(session_id)

    state = service.get_budget_state(session_id)
    assert (state.is_user_stopped, state.consecutive_wakes) == (False, 0)
