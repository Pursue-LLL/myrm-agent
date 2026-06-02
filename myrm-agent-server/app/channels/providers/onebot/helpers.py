"""Helper functions for OneBot v11 channel integration.

[INPUT]
- channels.types.messages::OutboundMessage, (POS: Core message type definitions. All cross-channel communication data structures are defined here; zero I/O, pure data.)

[OUTPUT]
- parse_onebot_message: Parse OneBot 消息数组为纯text和媒体附件
- build_onebot_message: 将 OutboundMessage Convert为 OneBot 消息数组

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

    # 2. Handle Media
    for attachment in msg.media:
        if attachment.media_type == MediaType.IMAGE:
            segments.append({"type": "image", "data": {"file": attachment.url or f"file://{attachment.path}"}})
        elif attachment.media_type == MediaType.AUDIO:
            segments.append({"type": "record", "data": {"file": attachment.url or f"file://{attachment.path}"}})
        elif attachment.media_type == MediaType.VIDEO:
            segments.append({"type": "video", "data": {"file": attachment.url or f"file://{attachment.path}"}})
        # Document/File sending in OneBot usually requires a different API (upload_group_file),
        # but some clients support it via message segment. We skip it here for simplicity
        # or fallback to text link if URL is provided.

    # 3. Handle Text
    if msg.content:
        segments.append({"type": "text", "data": {"text": msg.content}})

    return segments
