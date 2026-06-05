"""Pure helper functions for DingTalk channel.

Stateless utilities for signature verification, event parsing, media type
detection, and filename extraction. All functions are side-effect-free.

[INPUT]
- app.channels.types::InboundMessage, MediaAttachment (POS: Channel domain types.)

[OUTPUT]
- ParsedCallback: Structured result from parse_callback for type-safe access.
- verify_signature: HMAC-SHA256 webhook signature verification.
- parse_callback: DingTalk event body → ParsedCallback fields.
- guess_upload_type: filename → DingTalk media upload type.
- normalize_file_type: filename → DingTalk file extension.
- filename_from_url: URL → filename.
- guess_filename: MediaAttachment → best-effort filename.

[POS]
app.channels.providers.dingtalk.helpers — Pure helper functions for DingTalk channel.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import mimetypes
import os
from pathlib import Path
from typing import TypedDict
from urllib.parse import urlparse

from pydantic import ValidationError

from app.channels.types import (
    MediaAttachment,
    MediaType,
)

from .models import DingTalkCallbackPayload

logger = logging.getLogger(__name__)


class ParsedCallback(TypedDict):
    """Structured result from parse_callback for type-safe access."""

    sender_id: str
    content: str
    chat_id: str
    is_group: bool
    mentioned: bool
    media: tuple[MediaAttachment, ...]
    metadata: dict[str, object]
    message_id: str


_IMAGE_EXTS = frozenset({".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"})
_AUDIO_EXTS = frozenset({".amr", ".mp3", ".wav", ".ogg", ".m4a", ".aac"})
_VIDEO_EXTS = frozenset({".mp4", ".mov", ".avi", ".mkv", ".webm"})


def verify_signature(app_secret: str, timestamp: str, sign: str) -> bool:
    """Verify DingTalk webhook HMAC-SHA256 signature and prevent replay attacks."""
    if not app_secret:
        return True

    import time

    try:
        # DingTalk timestamp is in milliseconds
        ts = int(timestamp) / 1000.0
        if abs(time.time() - ts) > 300:  # 5 minutes replay protection
            logger.warning("DingTalk signature verification failed: timestamp expired (replay attack protection)")
            return False
    except ValueError:
        return False

    string_to_sign = f"{timestamp}\n{app_secret}"
    hmac_code = hmac.new(
        app_secret.encode("utf-8"),
        string_to_sign.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).digest()
    expected = base64.b64encode(hmac_code).decode("utf-8")
    return hmac.compare_digest(expected, sign)


def _strip_at_mentions(text: str, at_users: list[dict[str, object]]) -> str:
    """Remove @mention prefixes from message text.

    DingTalk includes @username text in the content field for group messages.
    Only strips known @mentions from at_users to avoid removing legitimate @ symbols.
    """
    if not at_users:
        return text
    for user in at_users:
        nick = str(user.get("dingtalkId", ""))
        if nick:
            text = text.replace(f"@{nick}", "")
    return text.strip()


def parse_callback(
    body: dict[str, object],
    robot_code: str,
) -> ParsedCallback | None:
    """Parse a DingTalk robot callback/event into structured fields.

    Uses Pydantic models for type-safe payload validation. Returns a
    ParsedCallback with typed keys, or None if the event contains no
    actionable content.
    """
    try:
        payload = DingTalkCallbackPayload.model_validate(body)
    except ValidationError:
        logger.debug("DingTalk callback payload validation failed")
        return None

    msg_type = payload.msgtype
    sender_id = payload.sender_staff_id or payload.sender_id
    is_group = payload.conversation_type == "2"

    content = ""
    media_list: list[MediaAttachment] = []

    if msg_type == "text" and payload.text:
        content = payload.text.content
    elif msg_type == "richText" and payload.rich_text:
        text_parts: list[str] = []
        for item in payload.rich_text.rich_text_list:
            if item.text:
                text_parts.append(item.text)
            if item.download_code and item.type == "picture":
                media_list.append(MediaAttachment(media_type=MediaType.IMAGE, url=item.download_code))
        content = "".join(text_parts)
    elif msg_type == "picture" and payload.content:
        if payload.content.download_code:
            media_list.append(
                MediaAttachment(
                    media_type=MediaType.IMAGE,
                    url=payload.content.download_code,
                )
            )
    elif msg_type == "file" and payload.content:
        if payload.content.file_name or payload.content.download_code:
            media_list.append(
                MediaAttachment(
                    media_type=MediaType.DOCUMENT,
                    url=payload.content.download_code or None,
                    filename=payload.content.file_name,
                )
            )

    at_user_dicts: list[dict[str, object]] = [u.model_dump(by_alias=True) for u in payload.at_users]

    if is_group and content:
        content = _strip_at_mentions(content, at_user_dicts)

    if not content.strip() and not media_list:
        return None

    mentioned = any(u.dingtalk_id == robot_code for u in payload.at_users)

    metadata: dict[str, object] = {
        "msgtype": msg_type,
        "conversationType": payload.conversation_type,
        "webhookUrl": payload.session_webhook,
        "webhookExpiredTime": payload.session_webhook_expired_time,
    }

    return ParsedCallback(
        sender_id=sender_id,
        content=content.strip(),
        chat_id=payload.conversation_id,
        is_group=is_group,
        mentioned=mentioned,
        media=tuple(media_list),
        metadata=metadata,
        message_id=payload.msg_id,
    )


def guess_upload_type(filename: str) -> str:
    """Map filename extension to DingTalk media upload type."""
    ext = Path(filename).suffix.lower()
    if ext in _IMAGE_EXTS:
        return "image"
    if ext in _AUDIO_EXTS:
        return "voice"
    if ext in _VIDEO_EXTS:
        return "video"
    return "file"


def normalize_file_type(filename: str) -> str:
    """Extract and normalize the file extension for DingTalk sampleFile API."""
    ext = Path(filename).suffix.lstrip(".").lower()
    if ext == "jpeg":
        return "jpg"
    return ext or "bin"


def filename_from_url(url: str) -> str:
    """Extract a reasonable filename from a URL path."""
    name = os.path.basename(urlparse(url).path)
    return name or "download.bin"


def guess_filename(att: MediaAttachment) -> str:
    """Best-effort filename for error messages."""
    if att.path:
        return Path(att.path).name
    if att.url:
        return filename_from_url(att.url)
    return "attachment"


def guess_mime_type(filename: str) -> str:
    """Guess MIME type from filename, defaulting to application/octet-stream."""
    return mimetypes.guess_type(filename)[0] or "application/octet-stream"
