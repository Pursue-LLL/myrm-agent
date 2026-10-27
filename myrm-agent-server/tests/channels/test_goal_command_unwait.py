"""IM `/goal unwait` hands the router the kickoff that puts the goal back to work, like `/goal resume` does."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.channels.routing.commands import RouterCommandsMixin
from app.channels.types import InboundMessage


def _make_msg(content: str = "") -> InboundMessage:
    return InboundMessage(channel="test", sender_id="user1", content=content)


def _make_host(handler: MagicMock) -> MagicMock:
    host = MagicMock()
    host._goal_handler = handler
    host._bus = MagicMock()
    host._bus.publish_outbound = AsyncMock()
    host._gate = MagicMock()
    host._gate.submit = MagicMock()
    host._active_tasks = {}
    return host


@pytest.mark.asyncio
async def test_unwait_submits_the_kickoff_that_puts_the_goal_back_to_work() -> None:
    kickoff_msg = _make_msg("goal text")
    handler = MagicMock()
    handler.handle_goal = AsyncMock(return_value="Goal no longer waiting")
    handler.get_resume_kickoff_message = AsyncMock(return_value=kickoff_msg)
    host = _make_host(handler)

    await RouterCommandsMixin._handle_goal_command(host, _make_msg(), "unwait")

    host._gate.submit.assert_called_once_with(kickoff_msg)
    handler.get_kickoff_message.assert_not_called()


@pytest.mark.asyncio
async def test_unwait_without_kickoff_submits_nothing() -> None:
    handler = MagicMock()
    handler.handle_goal = AsyncMock(return_value="Goal is not waiting")
    handler.get_resume_kickoff_message = AsyncMock(return_value=None)
    host = _make_host(handler)

    await RouterCommandsMixin._handle_goal_command(host, _make_msg(), "unwait")

    host._gate.submit.assert_not_called()
