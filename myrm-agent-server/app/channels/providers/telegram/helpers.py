"""Telegram module-level helpers, constants, and data structures.

[INPUT]
- channels.types::ActionButton, InboundMessage, OutboundMessage

[OUTPUT]
- BotCommand, _MediaGroupBuffer, build_inline_keyboard, send_media_attachment

[POS]
Telegram module-level utility functions, constants, and data structures.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path

from app.channels.types import (
    ActionButton,
    InboundMessage,
    MediaAttachment,
    MediaType,
    OutboundMessage,
    SelectMenu,
)

from .api import TelegramClient

logger = logging.getLogger(__name__)

POLL_TIMEOUT = 30
SEND_TIMEOUT = 15.0
MAX_TEXT_LENGTH = 4096

_CALLBACK_DATA_MAX = 64

_POLL_BACKOFF_INITIAL = 1.0
_POLL_BACKOFF_MAX = 30.0
_POLL_BACKOFF_FACTOR = 2.0

_MAX_CONFLICT_RETRIES = 5
_CONFLICT_RETRY_DELAY = 10.0
_DEGRADED_THRESHOLD = 3


@dataclass(frozen=True, slots=True)
class BotCommand:
    """A Telegram bot command for setMyCommands registration."""

    command: str
    description: str


@dataclass(slots=True)
class _MediaGroupBuffer:
    """Buffer for accumulating messages belonging to the same Telegram media group."""

    messages: list[InboundMessage] = field(default_factory=list)
    created_at: float = field(default_factory=time.monotonic)
    event: asyncio.Event = field(default_factory=asyncio.Event)


def build_inline_keyboard(msg: OutboundMessage) -> dict[str, object] | None:
    """Build Telegram InlineKeyboardMarkup from QuickReplies and Components.

    Returns None if no interactive elements are present.
    """
    rows: list[list[dict[str, str]]] = []

    for qr in msg.quick_replies:
        rows.append([{"text": qr.label, "callback_data": f"qr:{qr.text[: _CALLBACK_DATA_MAX - 3]}"}])

    for row in msg.components:
        kb_row: list[dict[str, str]] = []
        for comp in row:
            if isinstance(comp, ActionButton):
                if comp.url:
                    kb_row.append({"text": comp.label, "url": comp.url})
                else:
                    kb_row.append({"text": comp.label, "callback_data": f"act:{comp.action_id[: _CALLBACK_DATA_MAX - 4]}"})
            elif isinstance(comp, SelectMenu):
                for opt in comp.options[:5]:
                    kb_row.append({"text": opt.label, "callback_data": f"sel:{opt.value[: _CALLBACK_DATA_MAX - 4]}"})
        if kb_row:
            rows.append(kb_row)

    return {"inline_keyboard": rows} if rows else None


_SEND_METHOD = {
    MediaType.IMAGE: "send_photo",
    MediaType.VIDEO: "send_video",
}


async def send_media_attachment(
    client: TelegramClient,
    chat_id: str,
    attachment: MediaAttachment,
    reply_to_id: str | None,
    *,
    notification_kwargs: dict[str, bool] | None = None,
) -> None:
    """Send a single media attachment via the appropriate Telegram Bot API method.

    Intelligently routes AUDIO media based on MIME type (voice vs audio vs document)
    and automatically falls back to send_document if size exceeds limits.
    """
    from .api import get_recommended_send_method
    from .exceptions import AudioFileTooLargeError, VoiceMessageTooLargeError

    reply_to = int(reply_to_id) if reply_to_id else None
    source = attachment.url or (attachment.path and Path(attachment.path).read_bytes())
    if not source:
        logger.warning("TelegramChannel: skipping media with no url or path")
        return

    caption_prefix = ""

    if attachment.media_type == MediaType.AUDIO:
        mime = attachment.mime_type or "audio/ogg"
        size = len(source) if isinstance(source, bytes) else None
        method_name = get_recommended_send_method(mime, size)

        if method_name == "send_document" and size is not None:
            caption_prefix = " Audio file (size limit exceeded)\n"
            logger.warning("TelegramChannel: Audio file %s bytes exceeds limit, sending as document", f"{size:,}")
    else:
        method_name = _SEND_METHOD.get(attachment.media_type, "send_document")

    method = getattr(client, method_name)

    kwargs: dict[str, object] = {
        "caption": f"{caption_prefix}{attachment.caption or ''}".strip() or None,
        "reply_to_message_id": reply_to,
    }
    if notification_kwargs:
        kwargs.update(notification_kwargs)
    if attachment.filename:
        kwargs["filename"] = attachment.filename
    if attachment.media_type == MediaType.AUDIO and attachment.mime_type:
        kwargs["mime_type"] = attachment.mime_type

    try:
        await method(chat_id, source, **kwargs)
    except (VoiceMessageTooLargeError, AudioFileTooLargeError) as e:
        logger.warning("TelegramChannel: %s, fallback to sendDocument", e)
        await client.send_document(
            chat_id,
            source,
            filename=attachment.filename or "audio.ogg",
            mime_type=attachment.mime_type or "audio/ogg",
            caption=f" Audio file (size limit exceeded)\n{attachment.caption or ''}".strip() or None,
            reply_to_message_id=reply_to,
            disable_notification=notification_kwargs.get("disable_notification") if notification_kwargs else None,
        )
