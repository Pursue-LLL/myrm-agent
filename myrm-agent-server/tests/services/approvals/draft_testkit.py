"""Builders shared by the tests of held channel replies (``outbound_draft`` approvals)."""

from __future__ import annotations

from app.channels.types import ActionButton, MediaAttachment, OutboundMessage

HANDOFF_BUTTON = ActionButton(label="Continue in browser", action_id="web:continue_chat", url="https://example.test/chat/abc")


def held_reply(*media: MediaAttachment, content: str = "hello") -> OutboundMessage:
    return OutboundMessage(
        channel="telegram",
        recipient_id="peer-1",
        content=content,
        user_id="owner-1",
        media=media,
        components=((HANDOFF_BUTTON,),),
        reply_to_id="m-1",
        thread_id="th-1",
        metadata={"locale": "zh"},
    )


def draft_payload(reply: OutboundMessage, *, draft_content: str | None = None, **extra: object) -> dict[str, object]:
    """Payload as the router stores it: the text as ``draft_content``, the rest of the reply frozen in ``outbound``."""
    return {"draft_content": reply.content if draft_content is None else draft_content, "outbound": reply.to_dict(), **extra}
