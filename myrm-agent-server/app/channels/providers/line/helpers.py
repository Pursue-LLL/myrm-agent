"""LINE channel — typed structures, constants, and shared utilities.

[INPUT]

[OUTPUT]
- TypedDict webhook structures for LINE Messaging API payloads
- Constants: API endpoints, timeouts, text limits
- _ReplyToken: reply-token with expiry tracking
- _MEDIA_TYPE_MAP: LINE message type → MediaType mapping

[POS]
LINE webhook type definitions and constants. Referenced by channel.py.
"""

from __future__ import annotations

import time
from typing import TypedDict

from app.channels.types import MediaType

_API_BASE = "https://api.line.me/v2/bot"
_DATA_API_BASE = "https://api-data.line.me/v2/bot"
_SEND_TIMEOUT = 15.0
_HEALTH_TIMEOUT = 10.0
_LOADING_TIMEOUT = 5.0
_MAX_TEXT_LENGTH = 5000
_REPLY_TOKEN_MAX_AGE = 25.0
_MAX_MESSAGES_PER_REQUEST = 5
_MAX_QUICK_REPLY_ITEMS = 13
_QUICK_REPLY_LABEL_MAX = 20


# ---------------------------------------------------------------------------
# LINE webhook typed structures
# ---------------------------------------------------------------------------


class _Source(TypedDict, total=False):
    type: str
    userId: str
    groupId: str
    roomId: str


class _Mentionee(TypedDict, total=False):
    index: int
    length: int
    type: str
    isSelf: bool
    userId: str


class _Mention(TypedDict, total=False):
    mentionees: list[_Mentionee]


class _Message(TypedDict, total=False):
    id: str
    type: str
    text: str
    quoteToken: str
    fileName: str
    mention: _Mention
    contentProvider: dict[str, str]


class _Postback(TypedDict, total=False):
    data: str


class _Event(TypedDict, total=False):
    type: str
    replyToken: str
    source: _Source
    message: _Message
    postback: _Postback
    timestamp: int


class _ReplyToken:
    __slots__ = ("created_at", "token")

    def __init__(self, token: str) -> None:
        self.token = token
        self.created_at = time.monotonic()

    @property
    def expired(self) -> bool:
        return (time.monotonic() - self.created_at) >= _REPLY_TOKEN_MAX_AGE


_MEDIA_TYPE_MAP: dict[str, MediaType] = {
    "image": MediaType.IMAGE,
    "video": MediaType.VIDEO,
    "audio": MediaType.AUDIO,
    "file": MediaType.DOCUMENT,
}


def resolve_chat_id(source: _Source) -> str:
    """Extract the chat ID from a LINE event source."""
    src_type = source.get("type", "")
    if src_type == "group":
        return source.get("groupId", "")
    if src_type == "room":
        return source.get("roomId", "")
    return source.get("userId", "")
