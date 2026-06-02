"""Pure helper functions for QQ channel.

Stateless utilities for event parsing, URL sanitization, and media type detection.
All functions are side-effect-free and easily testable.

[INPUT]
- app.channels.types::InboundMessage, MediaAttachment (POS: Channel domain types.)

[OUTPUT]
- parse_event: QQ event → InboundMessage
- sanitize_urls: Replace dots in URL domains with fullwidth period for group messages
- qq_file_type: Determine QQ rich media file_type from MediaAttachment
- is_supported_event: Check if event type is supported
- is_group_event: Check if event is from a group
- parse_sender_id: Extract sender ID from event
- parse_attachments: Parse media attachments from event

[POS]
app.channels.providers.qq.helpers — Pure helper functions for QQ channel.
"""

from __future__ import annotations

import re

from app.channels.types import (
    MediaAttachment,
    MediaType,
)

QQ_FILE_TYPE_IMAGE = 1
QQ_FILE_TYPE_VIDEO = 2
QQ_FILE_TYPE_AUDIO = 3
QQ_FILE_TYPE_FILE = 4

_SUPPORTED_EVENT_TYPES = frozenset(
    {
        "GROUP_AT_MESSAGE_CREATE",
        "AT_MESSAGE_CREATE",
        "C2C_MESSAGE_CREATE",
        "DIRECT_MESSAGE_CREATE",
    }
)

_GROUP_EVENT_TYPES = frozenset(
    {
        "GROUP_AT_MESSAGE_CREATE",
        "AT_MESSAGE_CREATE",
    }
)

_URL_RE = re.compile(
    r"(?i)"
    r"https?://"
    r"(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}"
    r"(?:[/?#]\S*)?",
)


def is_supported_event(event_type: str) -> bool:
    return event_type in _SUPPORTED_EVENT_TYPES


def is_group_event(event_type: str) -> bool:
    return event_type in _GROUP_EVENT_TYPES


def parse_sender_id(author: dict[str, object]) -> str:
    return str(author.get("member_openid", "") or author.get("user_openid", "") or author.get("id", ""))


def parse_attachments(raw_attachments: list[dict[str, object]]) -> list[MediaAttachment]:
    result: list[MediaAttachment] = []
    for att in raw_attachments:
        ct = str(att.get("content_type", ""))
        if ct.startswith("image/"):
            mt = MediaType.IMAGE
        elif ct.startswith("audio/"):
            mt = MediaType.AUDIO
        elif ct.startswith("video/"):
            mt = MediaType.VIDEO
        else:
            mt = MediaType.DOCUMENT
        result.append(
            MediaAttachment(
                media_type=mt,
                url=str(att.get("url", "")),
                filename=str(att.get("filename", "")),
                mime_type=ct,
            )
        )
    return result


def qq_file_type(attachment: MediaAttachment) -> int:
    """Map MediaAttachment to QQ rich media file_type."""
    if attachment.media_type == MediaType.IMAGE:
        return QQ_FILE_TYPE_IMAGE
    if attachment.media_type == MediaType.VIDEO:
        return QQ_FILE_TYPE_VIDEO
    if attachment.media_type == MediaType.AUDIO:
        return QQ_FILE_TYPE_FILE  # QQ restricts audio; send as file
    return QQ_FILE_TYPE_FILE


def sanitize_urls(text: str) -> str:
    """Replace dots in URL domains with fullwidth period to bypass QQ's URL filter.

    QQ group messages containing URLs are rejected by the platform.
    This replaces '.' with '。' in the domain portion only, preserving
    the path/query/fragment. Only applied to group messages.
    """

    def _replace(match: re.Match[str]) -> str:
        url = match.group(0)
        idx = url.index("://")
        scheme = url[: idx + 3]
        rest = url[idx + 3 :]
        domain_end = len(rest)
        for i, ch in enumerate(rest):
            if ch in ("/", "?", "#"):
                domain_end = i
                break
        domain = rest[:domain_end].replace(".", "\u3002")
        return scheme + domain + rest[domain_end:]

    return _URL_RE.sub(_replace, text)


def build_message_url(api_base: str, target_id: str, chat_type: str) -> str:
    """Build the API URL for sending a message."""
    if chat_type == "group":
        return f"{api_base}/v2/groups/{target_id}/messages"
    if chat_type == "c2c":
        return f"{api_base}/v2/users/{target_id}/messages"
    return f"{api_base}/channels/{target_id}/messages"


def build_media_upload_url(api_base: str, target_id: str, chat_type: str) -> str:
    """Build the API URL for uploading media."""
    if chat_type == "group":
        return f"{api_base}/v2/groups/{target_id}/files"
    return f"{api_base}/v2/users/{target_id}/files"
