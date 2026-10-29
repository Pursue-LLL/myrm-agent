"""A fully populated ``InboundMessage`` for the tests that follow a message through the inbound journal."""

from __future__ import annotations

from app.channels.types import (
    ContextEntry,
    CorrelationContext,
    InboundMessage,
    MediaAttachment,
    MediaType,
    ReplyContext,
)


def full_message(*, image_path: str = "/tmp/a.png") -> InboundMessage:
    """A message with every persisted field set to a non-default value."""
    return InboundMessage(
        channel="telegram",
        sender_id="u1",
        content="look at this",
        sent_at=1_700_000_000.5,
        sent_timezone="Asia/Shanghai",
        chat_id="chat-9",
        user_id="user-77",
        sender_name="Alice",
        is_group=True,
        is_bot=True,
        mentioned=True,
        media=(
            MediaAttachment(
                media_type=MediaType.IMAGE,
                url="https://files.test/a.png",
                path=image_path,
                filename="a.png",
                mime_type="image/png",
                caption="a diagram",
                ephemeral=True,
            ),
            MediaAttachment(media_type=MediaType.DOCUMENT, url="https://files.test/b.pdf", filename="b.pdf"),
        ),
        metadata={"locale": "zh", "is_sticker": True, "nested": {"ids": [1, 2]}},
        reply_to_id="m-1",
        thread_id="t-1",
        context_messages=(ContextEntry(sender_id="u2", content="earlier", timestamp=1_699_999_990.0, sender_name="Bob"),),
        message_id="msg-5",
        resume_value={"decision": "approve", "request_id": "r1"},
        reply_to=ReplyContext(
            message_id="m-1",
            content="quoted text",
            media=(MediaAttachment(media_type=MediaType.AUDIO, url="https://files.test/c.ogg"),),
            sender_id="u3",
            sender_name="Carol",
            timestamp=1_699_999_000.0,
        ),
        correlation_context=CorrelationContext(
            channel="telegram", chat_id="chat-9", thread_id="t-1", user_id="user-77", trace_id="tr-1", locale="zh"
        ),
    )
