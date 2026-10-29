"""Typed shape of the JSON wire form of ``InboundMessage``, and the codec between the two.

[INPUT]
- channels.types.messages::InboundMessage, ContextEntry, ReplyContext, MediaAttachment, MediaType, CorrelationContext (POS: the dataclasses the wire form mirrors)
- channels.types.outbound_wire::MediaWire, CorrelationWire (POS: the media and correlation shapes both wire forms share)

[OUTPUT]
- InboundWire: the dict ``inbound_to_wire`` writes and ``inbound_from_wire`` reads
- ContextEntryWire, ReplyContextWire: its nested parts
- inbound_to_wire, inbound_from_wire: the codec

[POS]
What the inbound journal persists so a message replayed after a restart is the message the user sent. Each shape lists
exactly the fields of the dataclass it mirrors, except ``channel_capabilities``: that is read from the live channel when
the replayed turn starts, so it is not persisted. A test keeps the shapes in step. Metadata values the JSON encoder
cannot represent are the caller's to flatten.
"""

from __future__ import annotations

import time
from typing import NotRequired, TypedDict

from .messages import ContextEntry, CorrelationContext, InboundMessage, MediaAttachment, MediaType, ReplyContext
from .outbound_wire import CorrelationWire, MediaWire


class ContextEntryWire(TypedDict):
    sender_id: str
    content: str
    timestamp: float
    sender_name: NotRequired[str | None]


class ReplyContextWire(TypedDict):
    message_id: str
    content: str
    media: NotRequired[list[MediaWire]]
    sender_id: NotRequired[str | None]
    sender_name: NotRequired[str | None]
    timestamp: NotRequired[float | None]


class InboundWire(TypedDict):
    channel: str
    sender_id: str
    content: str
    sent_at: NotRequired[float]
    sent_timezone: NotRequired[str]
    chat_id: NotRequired[str | None]
    user_id: NotRequired[str | None]
    sender_name: NotRequired[str | None]
    is_group: NotRequired[bool]
    is_bot: NotRequired[bool]
    mentioned: NotRequired[bool]
    media: NotRequired[list[MediaWire]]
    metadata: NotRequired[dict[str, object]]
    reply_to_id: NotRequired[str | None]
    thread_id: NotRequired[str | None]
    context_messages: NotRequired[list[ContextEntryWire]]
    message_id: NotRequired[str | None]
    resume_value: NotRequired[dict[str, object] | None]
    reply_to: NotRequired[ReplyContextWire | None]
    correlation_context: NotRequired[CorrelationWire | None]


def _media_to_wire(media: MediaAttachment) -> MediaWire:
    return {
        "media_type": media.media_type.value,
        "url": media.url,
        "path": media.path,
        "filename": media.filename,
        "mime_type": media.mime_type,
        "caption": media.caption,
        "ephemeral": media.ephemeral,
    }


def _media_from_wire(wire: MediaWire) -> MediaAttachment:
    return MediaAttachment(
        media_type=MediaType(wire["media_type"]),
        url=wire.get("url"),
        path=wire.get("path"),
        filename=wire.get("filename"),
        mime_type=wire.get("mime_type"),
        caption=wire.get("caption"),
        ephemeral=bool(wire.get("ephemeral", False)),
    )


def _reply_to_wire(reply: ReplyContext) -> ReplyContextWire:
    return {
        "message_id": reply.message_id,
        "content": reply.content,
        "media": [_media_to_wire(m) for m in reply.media],
        "sender_id": reply.sender_id,
        "sender_name": reply.sender_name,
        "timestamp": reply.timestamp,
    }


def _reply_to_from_wire(wire: ReplyContextWire) -> ReplyContext:
    return ReplyContext(
        message_id=wire["message_id"],
        content=wire["content"],
        media=tuple(_media_from_wire(m) for m in wire.get("media", [])),
        sender_id=wire.get("sender_id"),
        sender_name=wire.get("sender_name"),
        timestamp=wire.get("timestamp"),
    )


def _correlation_to_wire(context: CorrelationContext) -> CorrelationWire:
    return {
        "channel": context.channel,
        "chat_id": context.chat_id,
        "thread_id": context.thread_id,
        "user_id": context.user_id,
        "trace_id": context.trace_id,
        "locale": context.locale,
    }


def _correlation_from_wire(wire: CorrelationWire) -> CorrelationContext:
    return CorrelationContext(
        channel=wire["channel"],
        chat_id=wire.get("chat_id"),
        thread_id=wire.get("thread_id"),
        user_id=wire.get("user_id"),
        trace_id=wire.get("trace_id"),
        locale=wire.get("locale"),
    )


def inbound_to_wire(msg: InboundMessage) -> InboundWire:
    """The persistable form of ``msg``; every field but ``channel_capabilities`` is in it."""
    return {
        "channel": msg.channel,
        "sender_id": msg.sender_id,
        "content": msg.content,
        "sent_at": msg.sent_at,
        "sent_timezone": msg.sent_timezone,
        "chat_id": msg.chat_id,
        "user_id": msg.user_id,
        "sender_name": msg.sender_name,
        "is_group": msg.is_group,
        "is_bot": msg.is_bot,
        "mentioned": msg.mentioned,
        "media": [_media_to_wire(m) for m in msg.media],
        "metadata": dict(msg.metadata),
        "reply_to_id": msg.reply_to_id,
        "thread_id": msg.thread_id,
        "context_messages": [
            {"sender_id": e.sender_id, "content": e.content, "timestamp": e.timestamp, "sender_name": e.sender_name}
            for e in msg.context_messages
        ],
        "message_id": msg.message_id,
        "resume_value": dict(msg.resume_value) if msg.resume_value is not None else None,
        "reply_to": _reply_to_wire(msg.reply_to) if msg.reply_to else None,
        "correlation_context": _correlation_to_wire(msg.correlation_context) if msg.correlation_context else None,
    }


def inbound_from_wire(wire: InboundWire) -> InboundMessage:
    """Rebuild the message ``inbound_to_wire`` produced the wire form from."""
    reply_to = wire.get("reply_to")
    correlation = wire.get("correlation_context")
    return InboundMessage(
        channel=wire["channel"],
        sender_id=wire["sender_id"],
        content=wire["content"],
        sent_at=wire.get("sent_at", time.time()),
        sent_timezone=wire.get("sent_timezone", "UTC"),
        chat_id=wire.get("chat_id"),
        user_id=wire.get("user_id"),
        sender_name=wire.get("sender_name"),
        is_group=wire.get("is_group", False),
        is_bot=wire.get("is_bot", False),
        mentioned=wire.get("mentioned", False),
        media=tuple(_media_from_wire(m) for m in wire.get("media", [])),
        metadata=wire.get("metadata", {}),
        reply_to_id=wire.get("reply_to_id"),
        thread_id=wire.get("thread_id"),
        context_messages=tuple(
            ContextEntry(
                sender_id=e["sender_id"], content=e["content"], timestamp=e["timestamp"], sender_name=e.get("sender_name")
            )
            for e in wire.get("context_messages", [])
        ),
        message_id=wire.get("message_id"),
        resume_value=wire.get("resume_value"),
        reply_to=_reply_to_from_wire(reply_to) if reply_to else None,
        correlation_context=_correlation_from_wire(correlation) if correlation else None,
    )
