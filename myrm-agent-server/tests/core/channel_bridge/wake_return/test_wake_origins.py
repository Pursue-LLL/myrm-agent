"""What the IM bridge remembers of where each chat is being talked in, so a wake turn's reply can go back."""

from __future__ import annotations

import pytest

from app.channels.types import ContextEntry, InboundMessage, MediaAttachment, MediaType, ReplyContext
from app.core.channel_bridge.wake_return import WakeOrigins, get_wake_origins


def _msg(**fields: object) -> InboundMessage:
    return InboundMessage(
        channel=str(fields.get("channel", "telegram")),
        sender_id="u1",
        content=str(fields.get("content", "research it")),
        chat_id="room-1",
        thread_id="topic-7",
        user_id="owner",
        sender_name="Ann",
        is_group=True,
        metadata={"locale": "zh-CN", "chat_name": "Team room"},
    )


def test_a_chat_is_remembered_with_where_it_is_talked_in() -> None:
    origins = WakeOrigins()

    origins.remember("chat-db-1", _msg())

    origin = origins.get("chat-db-1")
    assert origin is not None
    assert (origin.channel, origin.chat_id, origin.thread_id, origin.sender_id, origin.user_id, origin.is_group) == (
        "telegram",
        "room-1",
        "topic-7",
        "u1",
        "owner",
        True,
    )
    assert origin.metadata == {"locale": "zh-CN", "chat_name": "Team room"}


def test_a_chat_nobody_talked_in_has_no_origin() -> None:
    assert WakeOrigins().get("chat-db-1") is None


def test_the_latest_message_of_a_chat_is_the_origin() -> None:
    origins = WakeOrigins()
    origins.remember("chat-db-1", _msg())
    origins.remember(
        "chat-db-1", InboundMessage(channel="telegram", sender_id="u1", content="x", chat_id="room-1", thread_id="topic-9")
    )

    origin = origins.get("chat-db-1")
    assert origin is not None and origin.thread_id == "topic-9"


def test_only_what_a_reply_needs_is_kept() -> None:
    origins = WakeOrigins()
    attachment = MediaAttachment(media_type=MediaType.IMAGE, path="/tmp/a.png", ephemeral=True)
    msg = InboundMessage(
        channel="telegram",
        sender_id="u1",
        content="x" * 2000,
        chat_id="room-1",
        media=(attachment,),
        context_messages=(ContextEntry(sender_id="u2", content="earlier chatter", timestamp=1.0),),
        reply_to=ReplyContext(message_id="m0", content="quoted"),
        resume_value={"decisions": []},
        metadata={"locale": "en", "raw_update": {"huge": "payload"}, "attempt": 3},
    )

    origins.remember("chat-db-1", msg)

    origin = origins.get("chat-db-1")
    assert origin is not None
    assert len(origin.content) == 500
    assert (origin.media, origin.context_messages, origin.reply_to, origin.resume_value) == ((), (), None, None)
    assert origin.metadata == {"locale": "en"}
    # The turn's own message is left as it was.
    assert len(msg.content) == 2000 and msg.media == (attachment,)


@pytest.mark.parametrize("channel", ["web", "chat", "voice"])
def test_a_conversation_inside_the_app_or_on_a_live_call_has_no_outside_to_return_to(channel: str) -> None:
    origins = WakeOrigins()

    origins.remember("chat-db-1", _msg(channel=channel))

    assert origins.get("chat-db-1") is None


def test_the_memory_is_bounded_and_the_chat_written_longest_ago_goes_first() -> None:
    origins = WakeOrigins(capacity=2)
    origins.remember("a", _msg())
    origins.remember("b", _msg())
    origins.remember("a", _msg())  # a is the most recent again
    origins.remember("c", _msg())

    assert (origins.get("a") is not None, origins.get("b") is not None, origins.get("c") is not None) == (True, False, True)


def test_every_turn_shares_one_memory() -> None:
    assert get_wake_origins() is get_wake_origins()
