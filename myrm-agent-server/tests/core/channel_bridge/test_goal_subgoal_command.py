"""IM `/subgoal` serves a session between turns from storage and registers no provider for it."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from myrm_agent_harness.toolkits.storage.local import LocalStorageBackend

from app.channels.i18n import get_text
from app.channels.protocols.goal_command import SubgoalSubcommand
from app.channels.types import InboundMessage
from app.core.channel_bridge.goal_handler import ChannelGoalCommandHandler
from app.services.agent.goals.goal_registry import GoalRegistry


@pytest.fixture
def chat_id(tmp_path: Path) -> Iterator[str]:
    cid = f"goal-subgoal-{uuid.uuid4().hex[:8]}"
    with (
        patch("app.platform_utils.get_storage_provider", return_value=LocalStorageBackend(str(tmp_path))),
        patch("app.core.channel_bridge.goal_handler.handler.resolve_chat_id", new=AsyncMock(return_value=cid)),
    ):
        yield cid


def _message() -> InboundMessage:
    return InboundMessage(channel="test", sender_id="user-1", content="/subgoal")


async def test_a_subgoal_added_between_turns_lands_on_the_stored_goal(chat_id: str) -> None:
    goal = await GoalRegistry.resolve_provider(chat_id).create_goal(chat_id, "Ship the report")

    reply = await ChannelGoalCommandHandler().handle_subgoal(_message(), SubgoalSubcommand.ADD, "collect the figures")

    assert reply == get_text(_message(), "subgoal_added", text="collect the figures")
    stored = await GoalRegistry.resolve_provider(chat_id).get_goal(goal.goal_id)
    assert stored is not None
    assert stored.subgoals is not None
    assert [subgoal["text"] for subgoal in stored.subgoals] == ["collect the figures"]
    assert GoalRegistry.get_provider(chat_id) is None
