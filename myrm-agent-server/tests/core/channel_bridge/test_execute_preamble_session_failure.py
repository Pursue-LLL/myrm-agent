"""A turn that cannot open its chat workspace ends with a failed-turn reply, so a delegated task is not reported as done."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.channels.types import InboundMessage, OutboundMessage
from app.core.channel_bridge.agent_executor.execute_preamble.session import resolve_channel_session_context
from app.core.channel_bridge.executor_helpers.topic_workspace_sync import ChannelWorkspaceSyncError

_SESSION = "app.core.channel_bridge.agent_executor.execute_preamble.session"


def _msg() -> InboundMessage:
    return InboundMessage(channel="telegram", sender_id="user-1", chat_id="chat-1", content="hi", metadata={"locale": "en"})


@pytest.mark.asyncio
@pytest.mark.parametrize("is_resume", [False, True])
async def test_a_workspace_that_cannot_be_opened_ends_the_turn_with_a_flagged_reply(is_resume: bool) -> None:
    failing = AsyncMock(side_effect=ChannelWorkspaceSyncError("sync failed"))
    with (
        patch(f"{_SESSION}.resolve_session_key", new=AsyncMock(return_value="telegram:chat-1")),
        patch(f"{_SESSION}._detect_cold_start", new=AsyncMock(return_value=False)),
        patch(f"{_SESSION}.maybe_backfill_channel_history", new=AsyncMock()),
        patch(f"{_SESSION}.persist_and_load_history", new=failing),
        patch(f"{_SESSION}.load_history_without_persist", new=failing),
    ):
        context = await resolve_channel_session_context(
            MagicMock(),
            _msg(),
            query="hi",
            is_resume=is_resume,
            topic_context=None,
            resolved_agent_id=None,
            resolved_profile=None,
            personal_settings_dict=None,
        )

    assert context.chat_id == ""
    (reply,) = context.pre_events
    assert isinstance(reply, OutboundMessage)
    assert reply.metadata["error_type"] == "workspace_unavailable"
