"""Signal channel — typed structures, constants, and pure helper functions.

[INPUT]

[OUTPUT]
- TypedDict envelope structures for Signal CLI REST API payloads
- Constants: timeouts, text limits, poll interval, WebSocket settings
- _render_mentions(): hydrate U+FFFC placeholders from mention metadata

[POS]
Signal envelope type definitions, constants (timeouts, WS settings), and pure functions. Referenced by channel.py and api.py.
"""

from __future__ import annotations

from typing import TypedDict

_SEND_TIMEOUT = 15.0
_TYPING_TIMEOUT = 5.0
_MAX_TEXT_LENGTH = 10_000
_POLL_INTERVAL = 2.0
_HEALTH_TIMEOUT = 10.0
_WS_PING_INTERVAL = 30
_WS_PING_TIMEOUT = 10
_WS_PROBE_TIMEOUT = 5.0


# ---------------------------------------------------------------------------
# Signal envelope typed structures
# ---------------------------------------------------------------------------


class _GroupInfo(TypedDict, total=False):
    groupId: str
    groupName: str


class _Mention(TypedDict, total=False):
    start: int
    length: int
    uuid: str
    number: str


class _Attachment(TypedDict, total=False):
    contentType: str
    filename: str
    id: str
    size: int


class _Reaction(TypedDict, total=False):
    emoji: str
    targetAuthor: str
    targetSentTimestamp: int
    isRemove: bool


class _DataMessage(TypedDict, total=False):
    timestamp: int
    message: str
    groupInfo: _GroupInfo
    attachments: list[_Attachment]
    mentions: list[_Mention]
    reaction: _Reaction
    quote: dict[str, object]


class _EditMessage(TypedDict, total=False):
    targetSentTimestamp: int
    dataMessage: _DataMessage


class _Envelope(TypedDict, total=False):
    sourceNumber: str
    sourceUuid: str
    source: str
    sourceName: str
    timestamp: int
    dataMessage: _DataMessage
    editMessage: _EditMessage
    syncMessage: dict[str, object] | None
    reactionMessage: _Reaction


class _ReceivePayload(TypedDict, total=False):
    envelope: _Envelope


# ---------------------------------------------------------------------------
# Mention rendering
# ---------------------------------------------------------------------------


def _render_mentions(text: str, mentions: list[_Mention] | None) -> str:
    """Replace Signal's U+FFFC placeholders with @name from mention metadata.

    Signal encodes inline mentions as the object replacement character (U+FFFC).
    This function hydrates them from the mention list, sorted by descending
    start position to preserve index stability during replacement.
    """
    if not mentions:
        return text

    sorted_mentions = sorted(mentions, key=lambda m: m.get("start", 0), reverse=True)
    result = text
    for m in sorted_mentions:
        start = m.get("start", 0)
        length = m.get("length", 1)
        label = m.get("number") or m.get("uuid") or "unknown"
        result = result[:start] + f"@{label}" + result[start + length :]
    return result
