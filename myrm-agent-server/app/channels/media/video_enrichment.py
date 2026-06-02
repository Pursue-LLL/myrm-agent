"""Video attachment enrichment for channel inbound messages.

Detects video attachments in InboundMessage and injects metadata + text
markers so the agent can acknowledge and process video content.

Follows the same pattern as ``sticker_vision.describe_sticker_inbound``
and ``voice.handler.transcribe_inbound``: a pure async function that
enriches an InboundMessage, called from Router._handle_merged.

Unlike sticker/audio enrichment which perform heavyweight analysis (vision/STT),
video enrichment is lightweight — it marks metadata and appends a text hint.
Actual video analysis is deferred to the agent's VideoAnalysisEngine via
business-layer processing (chat_utils._process_video_item) or agent tools
(file_read_tool with video support).

[INPUT]
- channels.types::InboundMessage, MediaType, MediaAttachment

[OUTPUT]
- has_video_attachment(): check for video media
- enrich_video_inbound(): mark video metadata and inject content hint

[POS]
Lightweight video attachment detection and metadata enrichment for channel router.
"""

from __future__ import annotations

import dataclasses
import logging

from app.channels.types import InboundMessage, MediaType

logger = logging.getLogger(__name__)


def has_video_attachment(msg: InboundMessage) -> bool:
    """Check if the message contains a video attachment."""
    return any(a.media_type == MediaType.VIDEO for a in msg.media)


def enrich_video_inbound(msg: InboundMessage) -> InboundMessage:
    """Enrich an InboundMessage with video metadata and content hint.

    Extracts video attachment info (URL/path, filename, MIME) into
    ``msg.metadata["video_attachments"]`` and prepends a text marker
    to ``msg.content`` so the agent knows a video is present.

    Returns the original message unchanged if no video attachments found.
    """
    video_attachments = [a for a in msg.media if a.media_type == MediaType.VIDEO]
    if not video_attachments:
        return msg

    video_infos: list[dict[str, str | None]] = []
    hints: list[str] = []

    for idx, att in enumerate(video_attachments, 1):
        source = att.url or att.path
        name = att.filename or f"video_{idx}"
        info: dict[str, str | None] = {
            "url": att.url,
            "path": att.path,
            "filename": att.filename,
            "mime_type": att.mime_type,
            "caption": att.caption,
        }
        video_infos.append(info)

        label = f"[Video: {name}]"
        if att.caption:
            label = f"[Video: {name} — {att.caption}]"
        if source:
            label = f"{label} ({source})"
        hints.append(label)

    new_metadata = dict(msg.metadata)
    new_metadata["video_attachments"] = video_infos
    new_metadata["has_video"] = True

    video_header = "\n".join(hints)
    content = msg.content
    if content:
        content = f"{video_header}\n{content}"
    else:
        content = video_header

    logger.info(
        "Video enrichment: %d video(s) detected for %s/%s",
        len(video_attachments),
        msg.channel,
        msg.sender_id,
    )
    return dataclasses.replace(msg, content=content, metadata=new_metadata)
