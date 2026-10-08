"""Helper functions for OneBot v11 channel integration.

[INPUT]
- channels.types.messages::OutboundMessage, (POS: Core message type definitions. All cross-channel communication data structures are defined here; zero I/O, pure data.)

[OUTPUT]
- parse_onebot_message: Parse OneBot 消息数组为纯text和媒体附件
- build_onebot_message: 将 OutboundMessage Convert为 OneBot 消息数组
- can_send_media: Whether an attachment can ride in a OneBot message segment

[POS]
Pure-function helpers for the OneBot channel. Handles bidirectional conversion between
OneBot v11 message segments and framework message objects.
"""

from __future__ import annotations

import logging

from app.channels.types.messages import (
    MediaAttachment,
    MediaType,
    OutboundMessage,
)

logger = logging.getLogger(__name__)

# Documents and other files need a separate upload API that this channel does not use.
_MEDIA_SEGMENTS: dict[MediaType, str] = {
    MediaType.IMAGE: "image",
    MediaType.AUDIO: "record",
    MediaType.VIDEO: "video",
}


def can_send_media(attachment: MediaAttachment) -> bool:
    """Whether the attachment can ride in a message segment: an image, voice or video with a URL or local file."""
    return attachment.media_type in _MEDIA_SEGMENTS and bool(attachment.url or attachment.path)


def parse_onebot_message(message: list[dict[str, object]] | str) -> tuple[str, list[MediaAttachment]]:
    """Parse OneBot v11 message into plain text and media attachments.

    Supports both array format (recommended) and string format (CQ codes).
    """
    text_parts: list[str] = []
    media_list: list[MediaAttachment] = []

    if isinstance(message, str):
        # Fallback for simple string messages (ignores CQ codes for now,
        # modern clients like NapCat send arrays)
        return message, []

    for segment in message:
        seg_type = segment.get("type")
        data = segment.get("data", {})

        if seg_type == "text":
            text_parts.append(data.get("text", ""))
        elif seg_type == "at":
            # Convert @ to text representation
            qq = data.get("qq")
            if qq == "all":
                text_parts.append("@全体成员 ")
            else:
                text_parts.append(f"@{qq} ")
        elif seg_type == "image":
            url = data.get("url") or data.get("file")
            if url:
                media_list.append(
                    MediaAttachment(
                        media_type=MediaType.IMAGE,
                        url=url,
                    )
                )
        elif seg_type == "record":
            url = data.get("url") or data.get("file")
            if url:
                media_list.append(
                    MediaAttachment(
                        media_type=MediaType.AUDIO,
                        url=url,
                    )
                )
        elif seg_type == "video":
            url = data.get("url") or data.get("file")
            if url:
                media_list.append(
                    MediaAttachment(
                        media_type=MediaType.VIDEO,
                        url=url,
                    )
                )
        elif seg_type == "reply":
            # Handled separately in channel.py for ReplyContext
            pass

    return "".join(text_parts).strip(), media_list


def build_onebot_message(msg: OutboundMessage) -> list[dict[str, object]]:
    """Convert OutboundMessage to OneBot v11 message array."""
    segments: list[dict[str, object]] = []

    # 1. Handle Reply
    if msg.reply_to_id:
        segments.append({"type": "reply", "data": {"id": msg.reply_to_id}})

    # 2. Handle Media (the channel reports the attachments that cannot ride in a segment)
    for attachment in msg.media:
        if can_send_media(attachment):
            segments.append(
                {
                    "type": _MEDIA_SEGMENTS[attachment.media_type],
                    "data": {"file": attachment.url or f"file://{attachment.path}"},
                }
            )

    # 3. Handle Text
    if msg.content:
        segments.append({"type": "text", "data": {"text": msg.content}})

    return segments
