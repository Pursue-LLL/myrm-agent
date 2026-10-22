"""A FAQ hit is delivered as an ordinary reply routed back to the asking chat, without running the agent."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.channels.types import InboundMessage, OutboundMessage
from app.core.channel_bridge.agent_executor.executor import ChannelAgentExecutor

_EXECUTOR = "app.core.channel_bridge.agent_executor.executor"


def _inbound() -> InboundMessage:
    return InboundMessage(
        channel="telegram",
        sender_id="user-1",
        content="What are your opening hours?",
        sent_at=1.0,
        sent_timezone="UTC",
        chat_id="chat-1",
        user_id="user-1",
        message_id="msg-7",
        thread_id="thread-3",
        is_group=False,
        mentioned=False,
        metadata={"locale": "en"},
    )


@pytest.mark.asyncio
async def test_faq_answer_is_routed_back_to_the_asking_chat() -> None:
    prepare = AsyncMock()
    with (
        patch.object(ChannelAgentExecutor, "_try_faq_intercept", new=AsyncMock(return_value="We open at 9.")),
        patch(f"{_EXECUTOR}.prepare_channel_execution", new=prepare),
    ):
        replies = [
            event
            async for event in ChannelAgentExecutor().execute_stream(
                _inbound(), "user-1", topic_context=SimpleNamespace(agent_id="agent-1")
            )
        ]

    assert len(replies) == 1
    reply = replies[0]
    assert isinstance(reply, OutboundMessage)
    assert reply.content == "We open at 9."
    assert reply.channel == "telegram"
    assert reply.recipient_id == "chat-1"
    assert reply.reply_to_id == "msg-7"
    assert reply.thread_id == "thread-3"
    prepare.assert_not_called()
