"""Inbound-message builder shared by the SessionGate test files."""

from __future__ import annotations

from app.channels.types import InboundMessage, MediaAttachment


def make_message(
    content: str = "hello",
    *,
    channel: str = "telegram",
    sender_id: str = "user1",
    chat_id: str | None = None,
    is_group: bool = False,
    media: tuple[MediaAttachment, ...] = (),
    thread_id: str | None = None,
    mentioned: bool = False,
    message_id: str | None = None,
) -> InboundMessage:
    metadata: dict[str, object] = {}
    if message_id:
        metadata["message_id"] = message_id
    return InboundMessage(
        channel=channel,
        sender_id=sender_id,
        content=content,
        chat_id=chat_id,
        is_group=is_group,
        media=media,
        thread_id=thread_id,
        mentioned=mentioned,
        metadata=metadata,
    )
