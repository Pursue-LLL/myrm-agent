"""IM `/goal clear` and `/goal pause` act on the same goals, and stop the same work, as the web card."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from myrm_agent_harness.agent.goals.types import GoalStatus
from myrm_agent_harness.toolkits.storage.local import LocalStorageBackend

from app.channels.i18n import get_text
from app.channels.types import InboundMessage
from app.core.channel_bridge.goal_handler import ChannelGoalCommandHandler
from app.services.agent.gateway import AgentGateway
from app.services.agent.goals.goal_registry import GoalRegistry

_OBJECTIVE = "Ship the report"


@pytest.fixture
def chat_id(tmp_path: Path) -> Iterator[str]:
    cid = f"goal-clear-{uuid.uuid4().hex[:8]}"
    with patch("app.platform_utils.get_storage_provider", return_value=LocalStorageBackend(str(tmp_path))):
        yield cid
    GoalRegistry.unregister(cid)


@pytest.fixture
def gateway() -> Iterator[MagicMock]:
    """A gateway that has a live turn for every chat."""
    mock = MagicMock(spec=AgentGateway)
    mock.get_active_message_id.return_value = None
    mock.interrupt_session.return_value = True
    with patch("app.services.agent.goals.goal_controls.get_agent_gateway", return_value=mock):
        yield mock


async def _clear(chat_id: str) -> tuple[str, InboundMessage]:
    msg = InboundMessage(channel="test", sender_id="user-1", content="/goal clear")
    return await ChannelGoalCommandHandler()._clear_goal(msg, chat_id), msg  # noqa: SLF001 - command under test


@pytest.mark.parametrize(
    "status",
    [GoalStatus.ACTIVE, GoalStatus.PAUSED, GoalStatus.BUDGET_LIMITED, GoalStatus.NEEDS_HUMAN_REVIEW, GoalStatus.WAIT],
)
async def test_clear_cancels_every_open_goal(chat_id: str, status: GoalStatus) -> None:
    provider = GoalRegistry.get_or_create_provider(chat_id)
    goal = await provider.create_goal(chat_id, _OBJECTIVE)
    if status is not GoalStatus.ACTIVE:
        await provider.update_status(goal.goal_id, status)

    reply, msg = await _clear(chat_id)

    assert reply == get_text(msg, "goal_cleared", objective=_OBJECTIVE)
    cancelled = await provider.get_goal(goal.goal_id)
    assert cancelled is not None
    assert cancelled.status is GoalStatus.CANCELLED


async def test_clear_leaves_a_finished_goal_alone(chat_id: str) -> None:
    provider = GoalRegistry.get_or_create_provider(chat_id)
    goal = await provider.create_goal(chat_id, _OBJECTIVE)
    await provider.update_status(goal.goal_id, GoalStatus.COMPLETE)

    reply, msg = await _clear(chat_id)

    assert reply == get_text(msg, "no_active_goal_to_clear")
    kept = await provider.get_goal(goal.goal_id)
    assert kept is not None
    assert kept.status is GoalStatus.COMPLETE


async def test_clear_stops_the_turn_of_a_working_goal(chat_id: str, gateway: MagicMock) -> None:
    provider = GoalRegistry.get_or_create_provider(chat_id)
    await provider.create_goal(chat_id, _OBJECTIVE)

    await _clear(chat_id)

    gateway.interrupt_session.assert_called_once_with(chat_id)


async def test_clear_of_a_paused_goal_leaves_the_chat_turn_alone(chat_id: str, gateway: MagicMock) -> None:
    provider = GoalRegistry.get_or_create_provider(chat_id)
    goal = await provider.create_goal(chat_id, _OBJECTIVE)
    await provider.update_status(goal.goal_id, GoalStatus.PAUSED)

    await _clear(chat_id)

    gateway.interrupt_session.assert_not_called()


async def test_pause_stops_the_turn_and_keeps_the_note(chat_id: str, gateway: MagicMock) -> None:
    provider = GoalRegistry.get_or_create_provider(chat_id)
    goal = await provider.create_goal(chat_id, _OBJECTIVE)
    msg = InboundMessage(channel="test", sender_id="user-1", content="/goal pause waiting for review")

    reply = await ChannelGoalCommandHandler()._pause_goal(msg, chat_id, "waiting for review")  # noqa: SLF001 - command under test

    assert reply == get_text(msg, "goal_paused", objective=_OBJECTIVE)
    gateway.interrupt_session.assert_called_once_with(chat_id)
    paused = await provider.get_goal(goal.goal_id)
    assert paused is not None
    assert paused.status is GoalStatus.PAUSED
    assert paused.metadata["pause_reason"] == "waiting for review"
