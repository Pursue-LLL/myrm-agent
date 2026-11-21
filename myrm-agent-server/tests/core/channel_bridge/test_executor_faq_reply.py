"""A FAQ hit is delivered as an ordinary reply routed back to the asking chat, without running the agent.

Only the agent that serves the topic answers from its FAQ: a topic with no agent, or one whose identity is frozen and so
runs on the default agent, goes straight to the agent run.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.channels.types import InboundMessage, OutboundMessage, TopicContext
from app.core.channel_bridge.agent_executor.execute_preamble.types import PrepareChannelExecutionResult
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


@pytest.fixture
def turn() -> Iterator[SimpleNamespace]:
    """The FAQ lookup answers every question; the preparation that follows a miss ends the turn before an agent runs."""
    faq = AsyncMock(return_value="We open at 9.")
    prepare = AsyncMock(return_value=PrepareChannelExecutionResult(pre_events=()))
    with (
        patch.object(ChannelAgentExecutor, "_try_faq_intercept", new=faq),
        patch(f"{_EXECUTOR}.prepare_channel_execution", new=prepare),
    ):
        yield SimpleNamespace(faq=faq, prepare=prepare)


async def _events(topic: TopicContext | None) -> list[object]:
    stream: AsyncIterator[object] = ChannelAgentExecutor().execute_stream(_inbound(), "user-1", topic_context=topic)
    return [event async for event in stream]


@pytest.mark.asyncio
async def test_faq_answer_is_routed_back_to_the_asking_chat(turn: SimpleNamespace) -> None:
    replies = await _events(TopicContext(topic_id="chat-1", agent_id="agent-1"))

    assert len(replies) == 1
    reply = replies[0]
    assert isinstance(reply, OutboundMessage)
    assert reply.content == "We open at 9."
    assert reply.channel == "telegram"
    assert reply.recipient_id == "chat-1"
    assert reply.reply_to_id == "msg-7"
    assert reply.thread_id == "thread-3"
    turn.prepare.assert_not_called()


@pytest.mark.asyncio
async def test_the_question_is_put_to_the_faq_of_the_agent_that_serves_the_topic(turn: SimpleNamespace) -> None:
    await _events(TopicContext(topic_id="chat-1", agent_id="agent-1"))

    turn.faq.assert_awaited_once_with(agent_id="agent-1", user_query="What are your opening hours?", channel="telegram")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "topic",
    [
        pytest.param(None, id="no-binding"),
        pytest.param(TopicContext(topic_id="chat-1"), id="binding-without-agent"),
        pytest.param(TopicContext(topic_id="chat-1", agent_id=""), id="empty-agent"),
        pytest.param(TopicContext(topic_id="chat-1", agent_id="agent-1", identity_revoked=True), id="frozen-identity"),
    ],
)
async def test_a_topic_no_agent_serves_is_not_answered_from_a_faq(turn: SimpleNamespace, topic: TopicContext | None) -> None:
    assert await _events(topic) == []

    turn.faq.assert_not_awaited()
    turn.prepare.assert_awaited_once()
