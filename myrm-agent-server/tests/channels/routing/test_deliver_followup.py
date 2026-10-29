"""A reply that no message just asked for is delivered the way the answer to a message is.

The real router delivers; the bus, the topic store, the web hand-off lookup and the data-plane ledger are recorders.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.channels.routing.router import AgentRouter
from app.channels.types import InboundMessage, OutboundMessage, ReplyMode, TopicContext


def _topics(topic: TopicContext | None) -> MagicMock:
    """A topic store that resolves one topic context for any chat (the chat-level binding)."""
    return MagicMock(resolve_topic=AsyncMock(return_value=topic), sync_topic_metadata=AsyncMock())


class _Delivery:
    """The router under test with everything outside delivery recorded."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, topic: TopicContext | None) -> None:
        self.bus = MagicMock(publish_outbound=AsyncMock())
        self.router = AgentRouter(
            bus=self.bus,
            pairing_store=MagicMock(),
            agent_executor=MagicMock(),
            topic_resolver=_topics(topic),
        )
        self.handoff_for: list[InboundMessage] = []
        self.draft = AsyncMock()

        async def with_handoff(result: OutboundMessage, msg: InboundMessage) -> OutboundMessage:
            self.handoff_for.append(msg)
            return result

        monkeypatch.setattr(self.router, "_attach_web_handoff", with_handoff)
        monkeypatch.setattr(self.router, "_create_outbound_draft", self.draft)
        monkeypatch.setattr("app.channels.routing.channel_data_plane.ChannelDataPlaneService.record_outbound", AsyncMock())

    @property
    def sent(self) -> list[OutboundMessage]:
        return [call.args[0] for call in self.bus.publish_outbound.await_args_list]


def _origin(*, chat_id: str | None = "chat-1", thread_id: str | None = None) -> InboundMessage:
    return InboundMessage(
        channel="telegram",
        sender_id="u1",
        content="run the research in the background",
        chat_id=chat_id,
        thread_id=thread_id,
        user_id="owner",
        metadata={"locale": "zh-CN"},
    )


@pytest.fixture
def delivery(monkeypatch: pytest.MonkeyPatch) -> _Delivery:
    return _Delivery(monkeypatch, topic=None)


@pytest.mark.asyncio
async def test_the_reply_goes_to_the_chat_and_thread_the_conversation_lives_in(delivery: _Delivery) -> None:
    origin = _origin(thread_id="topic-7")

    assert await delivery.router.deliver_followup(origin, "The research is done.") is True

    (sent,) = delivery.sent
    assert (sent.channel, sent.recipient_id, sent.thread_id, sent.user_id) == ("telegram", "chat-1", "topic-7", "owner")
    assert sent.content == "The research is done."
    assert sent.metadata is not None and sent.metadata["locale"] == "zh-CN"


@pytest.mark.asyncio
async def test_a_direct_message_without_a_chat_id_is_answered_to_the_sender(delivery: _Delivery) -> None:
    assert await delivery.router.deliver_followup(_origin(chat_id=None), "done") is True

    assert [sent.recipient_id for sent in delivery.sent] == ["u1"]


@pytest.mark.asyncio
async def test_the_reply_carries_the_web_hand_off_like_any_reply(delivery: _Delivery) -> None:
    origin = _origin()

    await delivery.router.deliver_followup(origin, "done")

    assert delivery.handoff_for == [origin]


@pytest.mark.asyncio
async def test_a_silent_reply_is_not_sent(delivery: _Delivery) -> None:
    assert await delivery.router.deliver_followup(_origin(), "[SILENT]") is False

    assert delivery.sent == []


@pytest.mark.asyncio
async def test_a_topic_that_was_disabled_since_gets_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    delivery = _Delivery(monkeypatch, TopicContext(topic_id="chat-1", enabled=False))

    assert await delivery.router.deliver_followup(_origin(), "done") is False

    assert delivery.sent == []
    delivery.draft.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_topic_that_holds_replies_for_review_gets_a_draft_and_the_reply_is_not_sent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    topic = TopicContext(topic_id="chat-1", reply_mode=ReplyMode.DRAFT_REVIEW)
    delivery = _Delivery(monkeypatch, topic)
    origin = _origin()

    assert await delivery.router.deliver_followup(origin, "Refund approved.") is False

    assert delivery.sent == []
    delivery.draft.assert_awaited_once()
    assert delivery.draft.await_args is not None
    held, held_for, held_chat, held_topic, placeholder = delivery.draft.await_args.args
    assert (held.content, held_for, held_chat, placeholder) == ("Refund approved.", origin, "chat-1", None)
    assert held_topic.reply_mode is ReplyMode.DRAFT_REVIEW


@pytest.mark.asyncio
async def test_a_reply_that_cannot_be_held_for_review_is_withheld_never_sent_unreviewed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    delivery = _Delivery(monkeypatch, TopicContext(topic_id="chat-1", reply_mode=ReplyMode.DRAFT_REVIEW))
    delivery.draft.side_effect = RuntimeError("approval store down")

    assert await delivery.router.deliver_followup(_origin(), "Refund approved.") is False

    assert delivery.sent == []
