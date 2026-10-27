"""IM `/goal resume` puts the goal back to work: it waits for a stopped turn, then hands the router a kickoff."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from myrm_agent_harness.agent.goals.types import GoalStatus
from myrm_agent_harness.toolkits.storage.local import LocalStorageBackend

from app.channels.i18n import get_text
from app.channels.types import InboundMessage
from app.core.channel_bridge.goal_handler import ChannelGoalCommandHandler
from app.services.agent.gateway import AgentGateway
from app.services.agent.goals import goal_controls
from app.services.agent.goals.goal_registry import GoalRegistry

_OBJECTIVE = "Ship the report"


@pytest.fixture
def chat_id(tmp_path: Path) -> Iterator[str]:
    cid = f"goal-resume-{uuid.uuid4().hex[:8]}"
    with (
        patch("app.platform_utils.get_storage_provider", return_value=LocalStorageBackend(str(tmp_path))),
        patch("app.core.channel_bridge.goal_handler._resolve_chat_id", new=AsyncMock(return_value=cid)),
    ):
        yield cid
    GoalRegistry.unregister(cid)


@pytest.fixture
def gateway() -> Iterator[MagicMock]:
    """An idle gateway that is not draining."""
    mock = MagicMock(spec=AgentGateway)
    mock.is_session_active.return_value = False
    mock.is_draining = False
    with (
        patch("app.services.agent.goals.goal_controls.get_agent_gateway", return_value=mock),
        patch.object(goal_controls, "_IDLE_POLL_SECONDS", 0.001),
        patch.object(goal_controls, "_IDLE_WAIT_SECONDS", 0.05),
    ):
        yield mock


def _message() -> InboundMessage:
    return InboundMessage(channel="test", sender_id="user-1", content="/goal resume")


async def _paused_goal(chat_id: str) -> str:
    provider = GoalRegistry.get_or_create_provider(chat_id)
    goal = await provider.create_goal(chat_id, _OBJECTIVE)
    await provider.update_status(goal.goal_id, GoalStatus.PAUSED)
    return goal.goal_id


async def _status(chat_id: str, goal_id: str) -> GoalStatus:
    goal = await GoalRegistry.get_or_create_provider(chat_id).get_goal(goal_id)
    assert goal is not None
    return goal.status


async def _resume(chat_id: str) -> str:
    return await ChannelGoalCommandHandler()._resume_goal(_message(), chat_id)  # noqa: SLF001 - command under test


async def test_resume_waits_for_the_stopped_turn_to_finish(chat_id: str, gateway: MagicMock) -> None:
    goal_id = await _paused_goal(chat_id)
    polls = iter([True, True])
    gateway.is_session_active.side_effect = lambda _sid: next(polls, False)

    reply = await _resume(chat_id)

    assert reply == get_text(_message(), "goal_resumed", objective=_OBJECTIVE)
    assert gateway.is_session_active.call_count == 3
    assert await _status(chat_id, goal_id) is GoalStatus.ACTIVE


async def test_resume_does_not_hang_on_a_turn_that_never_finishes(chat_id: str, gateway: MagicMock) -> None:
    goal_id = await _paused_goal(chat_id)
    gateway.is_session_active.return_value = True

    await _resume(chat_id)

    assert await _status(chat_id, goal_id) is GoalStatus.ACTIVE


async def test_resume_kickoff_carries_the_goal_objective(chat_id: str, gateway: MagicMock) -> None:
    await _paused_goal(chat_id)
    await _resume(chat_id)
    handler = ChannelGoalCommandHandler()

    kickoff = await handler.get_resume_kickoff_message(_message())

    assert kickoff is not None
    assert kickoff.content == _OBJECTIVE
    assert kickoff.channel == "test"


@pytest.mark.parametrize(
    "session_state",
    [{"is_session_active": True, "is_draining": False}, {"is_session_active": False, "is_draining": True}],
    ids=["session-busy", "app-draining"],
)
async def test_no_kickoff_when_the_session_cannot_take_a_turn(
    chat_id: str, gateway: MagicMock, session_state: dict[str, bool]
) -> None:
    await _paused_goal(chat_id)
    await _resume(chat_id)
    gateway.is_session_active.return_value = session_state["is_session_active"]
    gateway.is_draining = session_state["is_draining"]

    assert await ChannelGoalCommandHandler().get_resume_kickoff_message(_message()) is None


@pytest.mark.parametrize("status", [GoalStatus.PAUSED, GoalStatus.COMPLETE, GoalStatus.CANCELLED])
async def test_no_kickoff_when_the_goal_is_not_active(chat_id: str, gateway: MagicMock, status: GoalStatus) -> None:
    provider = GoalRegistry.get_or_create_provider(chat_id)
    goal = await provider.create_goal(chat_id, _OBJECTIVE)
    await provider.update_status(goal.goal_id, status)

    assert await ChannelGoalCommandHandler().get_resume_kickoff_message(_message()) is None


async def test_no_kickoff_without_a_goal(chat_id: str, gateway: MagicMock) -> None:
    assert await ChannelGoalCommandHandler().get_resume_kickoff_message(_message()) is None
