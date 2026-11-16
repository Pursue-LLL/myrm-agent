"""IM `/goal` commands between turns act on the goal in storage: the turn that created it has ended and left no provider registered."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from myrm_agent_harness.agent.goals.types import Goal, GoalStatus
from myrm_agent_harness.toolkits.storage.local import LocalStorageBackend

from app.channels.i18n import get_text
from app.channels.protocols.goal_command import GoalSubcommand
from app.channels.types import InboundMessage
from app.core.channel_bridge.goal_handler import ChannelGoalCommandHandler
from app.services.agent.gateway import AgentGateway
from app.services.agent.goals.goal_registry import GoalRegistry

_OBJECTIVE = "Ship the report"


@pytest.fixture
def chat_id(tmp_path: Path) -> Iterator[str]:
    cid = f"goal-between-{uuid.uuid4().hex[:8]}"
    with (
        patch("app.platform_utils.get_storage_provider", return_value=LocalStorageBackend(str(tmp_path))),
        patch("app.core.channel_bridge.goal_handler.handler.resolve_chat_id", new=AsyncMock(return_value=cid)),
    ):
        yield cid
    GoalRegistry.unregister(cid)


@pytest.fixture(autouse=True)
def gateway() -> Iterator[MagicMock]:
    """An idle gateway that is not draining."""
    mock = MagicMock(spec=AgentGateway)
    mock.is_session_active.return_value = False
    mock.is_session_interrupted.return_value = False
    mock.get_active_message_id.return_value = None
    mock.is_draining = False
    with patch("app.services.agent.goals.goal_controls.get_agent_gateway", return_value=mock):
        yield mock


def _message() -> InboundMessage:
    return InboundMessage(channel="test", sender_id="user-1", content="/goal")


async def _command(subcommand: GoalSubcommand, args: str = "") -> str:
    return await ChannelGoalCommandHandler().handle_goal(_message(), subcommand, args)


async def _goal_left_by_a_finished_turn(chat_id: str, status: GoalStatus = GoalStatus.ACTIVE) -> str:
    """Create a goal the way a turn does, then end that turn: storage keeps the goal, no provider stays registered."""
    provider = GoalRegistry.get_or_create_provider(chat_id)
    goal = await provider.create_goal(chat_id, _OBJECTIVE)
    if status is not GoalStatus.ACTIVE:
        await provider.update_status(goal.goal_id, status)
    GoalRegistry.unregister(chat_id)
    return goal.goal_id


async def _stored(chat_id: str, goal_id: str) -> Goal:
    goal = await GoalRegistry.resolve_provider(chat_id).get_goal(goal_id)
    assert goal is not None
    return goal


async def test_status_shows_the_stored_goal(chat_id: str) -> None:
    await _goal_left_by_a_finished_turn(chat_id)

    reply = await _command(GoalSubcommand.STATUS)

    assert _OBJECTIVE in reply
    assert GoalRegistry.get_provider(chat_id) is None


async def test_pause_pauses_the_stored_goal_and_keeps_the_note(chat_id: str) -> None:
    goal_id = await _goal_left_by_a_finished_turn(chat_id)

    reply = await _command(GoalSubcommand.PAUSE, "waiting for review")

    assert reply == get_text(_message(), "goal_paused", objective=_OBJECTIVE)
    paused = await _stored(chat_id, goal_id)
    assert paused.status is GoalStatus.PAUSED
    assert paused.metadata["pause_reason"] == "waiting for review"


async def test_resume_puts_the_stored_paused_goal_back_to_work(chat_id: str) -> None:
    goal_id = await _goal_left_by_a_finished_turn(chat_id, GoalStatus.PAUSED)

    reply = await _command(GoalSubcommand.RESUME)

    assert reply == get_text(_message(), "goal_resumed", objective=_OBJECTIVE)
    assert (await _stored(chat_id, goal_id)).status is GoalStatus.ACTIVE


async def test_resume_kickoff_is_built_from_the_stored_goal(chat_id: str) -> None:
    await _goal_left_by_a_finished_turn(chat_id)

    kickoff = await ChannelGoalCommandHandler().get_resume_kickoff_message(_message())

    assert kickoff is not None
    assert kickoff.content == _OBJECTIVE


async def test_clear_cancels_the_stored_goal(chat_id: str) -> None:
    goal_id = await _goal_left_by_a_finished_turn(chat_id, GoalStatus.PAUSED)

    reply = await _command(GoalSubcommand.CLEAR)

    assert reply == get_text(_message(), "goal_cleared", objective=_OBJECTIVE)
    assert (await _stored(chat_id, goal_id)).status is GoalStatus.CANCELLED


async def test_wait_puts_the_stored_goal_to_wait(chat_id: str) -> None:
    goal_id = await _goal_left_by_a_finished_turn(chat_id)

    reply = await _command(GoalSubcommand.WAIT, "CI is running")

    assert reply == get_text(_message(), "goal_wait", objective=_OBJECTIVE, reason="CI is running")
    assert (await _stored(chat_id, goal_id)).status is GoalStatus.WAIT


async def test_unwait_releases_the_stored_waiting_goal(chat_id: str) -> None:
    goal_id = await _goal_left_by_a_finished_turn(chat_id, GoalStatus.WAIT)

    reply = await _command(GoalSubcommand.UNWAIT)

    assert reply == get_text(_message(), "goal_unwait", objective=_OBJECTIVE)
    assert (await _stored(chat_id, goal_id)).status is GoalStatus.ACTIVE


async def test_budget_sets_the_turn_limit_of_the_stored_goal(chat_id: str) -> None:
    goal_id = await _goal_left_by_a_finished_turn(chat_id)

    reply = await _command(GoalSubcommand.BUDGET, "5")

    assert reply == get_text(_message(), "goal_budget_set", max_turns=5)
    budget = (await _stored(chat_id, goal_id)).budget
    assert budget is not None
    assert budget.max_turns == 5


async def test_constraint_is_added_to_the_stored_goal(chat_id: str) -> None:
    goal_id = await _goal_left_by_a_finished_turn(chat_id)

    reply = await _command(GoalSubcommand.CONSTRAINT, "no paid APIs")

    assert reply == get_text(_message(), "goal_constraint_added", constraint="no paid APIs")
    assert (await _stored(chat_id, goal_id)).constraints == ["no paid APIs"]


@pytest.mark.parametrize(
    ("subcommand", "key"),
    [
        (GoalSubcommand.STATUS, "no_goal_is_set"),
        (GoalSubcommand.PAUSE, "no_active_goal_to_pause"),
        (GoalSubcommand.WAIT, "no_active_goal_to_pause"),
        (GoalSubcommand.UNWAIT, "goal_not_waiting"),
        (GoalSubcommand.RESUME, "no_goal_to_resume"),
        (GoalSubcommand.CLEAR, "no_active_goal_to_clear"),
        (GoalSubcommand.BUDGET, "no_active_goal_budget"),
        (GoalSubcommand.CONSTRAINT, "no_active_goal_constraint"),
    ],
)
async def test_a_chat_without_a_goal_gets_the_answer_of_that_command(chat_id: str, subcommand: GoalSubcommand, key: str) -> None:
    reply = await _command(subcommand)

    assert reply == get_text(_message(), key)
    assert GoalRegistry.get_provider(chat_id) is None
