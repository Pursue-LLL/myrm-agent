"""iLink Bot protocol data types and serialization.

Pure data types (enums, dataclasses) and serialization helpers for the
iLink Bot protocol. Zero I/O, zero network dependencies.

[OUTPUT]
- MessageType, MessageState, ItemType, CDNMediaType, TypingStatus: enums
- ILinkCredentials, MediaInfo, TextItem, ImageItem, VoiceItem, FileItem, VideoItem: data
- MessageItem, ILinkMessage: composite message types
- serialize_item, parse_media_info, parse_item: serialization helpers (parse_item includes type/sub-key fallback)

[POS]
Pure data type definitions and serialization utilities for the iLink Bot protocol.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from enum import IntEnum

_logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://ilinkai.weixin.qq.com"


# ── Enums ──────────────────────────────────────────────────────────────


class MessageType(IntEnum):
    NONE = 0
    USER = 1
    BOT = 2


class MessageState(IntEnum):
    NEW = 0
    GENERATING = 1
    FINISH = 2


class ItemType(IntEnum):
    NONE = 0
    TEXT = 1
    IMAGE = 2
    VOICE = 3
    FILE = 4
    VIDEO = 5


class CDNMediaType(IntEnum):
    IMAGE = 1
    VIDEO = 2
    FILE = 3
    VOICE = 4


class TypingStatus(IntEnum):
    TYPING = 1
    CANCEL = 2


# ── Data classes ───────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class ILinkCredentials:
    bot_token: str
    ilink_bot_id: str
    base_url: str = DEFAULT_BASE_URL
    ilink_user_id: str | None = None


@dataclass(frozen=True, slots=True)
class MediaInfo:
    """CDN media reference with encryption info."""

    encrypt_query_param: str
    aes_key: str
    encrypt_type: int = 1


@dataclass(frozen=True, slots=True)
class TextItem:
    text: str


@dataclass(frozen=True, slots=True)
class ImageItem:
    url: str | None = None
    media: MediaInfo | None = None
    mid_size: int | None = None


@dataclass(frozen=True, slots=True)
class VoiceItem:
    media: MediaInfo | None = None
    encode_type: int | None = None
    sample_rate: int | None = None
    playtime: int | None = None
    text: str | None = None


@dataclass(frozen=True, slots=True)
class FileItem:
    media: MediaInfo | None = None
    file_name: str | None = None
    file_size: str | None = None


@dataclass(frozen=True, slots=True)
class VideoItem:
    media: MediaInfo | None = None
    video_size: int | None = None
    play_length: int | None = None


@dataclass(frozen=True, slots=True)
class MessageItem:
    type: int
    text_item: TextItem | None = None
    image_item: ImageItem | None = None
    voice_item: VoiceItem | None = None
    file_item: FileItem | None = None
    video_item: VideoItem | None = None


@dataclass(frozen=True, slots=True)
class ILinkMessage:
    from_user_id: str
    to_user_id: str
    message_type: int
    message_state: int
    item_list: tuple[MessageItem, ...]
    context_token: str | None = None
    message_id: int | None = None
    session_id: str | None = None
    group_id: str | None = None
    from_user_name: str | None = None


# ── Serialization helpers ──────────────────────────────────────────────


def serialize_item(item: MessageItem) -> dict[str, object]:
    """Serialize MessageItem to JSON dict for iLink API."""
    result: dict[str, object] = {"type": item.type}

    if item.text_item:
        result["text_item"] = {"text": item.text_item.text}
    elif item.image_item:
        img: dict[str, object] = {}
        if item.image_item.url:
            img["url"] = item.image_item.url
        if item.image_item.media:
            img["media"] = _serialize_media(item.image_item.media)
        if item.image_item.mid_size is not None:
            img["mid_size"] = item.image_item.mid_size
        result["image_item"] = img
    elif item.voice_item:
        voice: dict[str, object] = {}
        if item.voice_item.media:
            voice["media"] = _serialize_media(item.voice_item.media)
        result["voice_item"] = voice
    elif item.file_item:
        file_d: dict[str, object] = {}
        if item.file_item.media:
            file_d["media"] = _serialize_media(item.file_item.media)
        if item.file_item.file_name:
            file_d["file_name"] = item.file_item.file_name
        result["file_item"] = file_d
    elif item.video_item:
        video: dict[str, object] = {}
        if item.video_item.media:
            video["media"] = _serialize_media(item.video_item.media)
        result["video_item"] = video

    return result


def _serialize_media(media: MediaInfo) -> dict[str, object]:
    return {
        "encrypt_query_param": media.encrypt_query_param,
        "aes_key": media.aes_key,
        "encrypt_type": media.encrypt_type,
    }


def parse_media_info(raw: object) -> MediaInfo | None:
    """Parse MediaInfo from raw API dict."""
    if not isinstance(raw, dict):
        return None
    eqp = raw.get("encrypt_query_param", "")
    aes = raw.get("aes_key", "")
    if not isinstance(eqp, str) or not isinstance(aes, str):
        return None
    return MediaInfo(
        encrypt_query_param=eqp,
        aes_key=aes,
        encrypt_type=int(raw.get("encrypt_type", 1)),
    )


def parse_item(item_data: dict[str, object]) -> MessageItem | None:
    """Parse a single MessageItem from raw API dict.

    Primary strategy: parse the sub-key indicated by ``type``.
    Fallback: when the declared type's sub-key is empty/missing, scan all
    known sub-keys so a type/sub-key mismatch (e.g. type=VIDEO but
    payload carries ``file_item``) does not silently drop the message.
    """
    item_type = int(item_data.get("type", 0))

    result = _parse_by_type(item_data, item_type)
    if result is not None:
        return result

    for key, effective_type, parser in _SUBKEY_PARSERS:
        if effective_type == item_type:
            continue
        raw = item_data.get(key)
        if not isinstance(raw, dict) or not raw:
            continue
        fallback = parser(raw, effective_type)
        if fallback is not None:
            _logger.warning(
                "iLink parse_item: type=%d but used fallback sub-key '%s' (effective_type=%d)",
                item_type,
                key,
                effective_type,
            )
            return fallback

    return None


def _parse_by_type(item_data: dict[str, object], item_type: int) -> MessageItem | None:
    """Parse using the declared item_type."""
    if item_type == ItemType.TEXT:
        raw = item_data.get("text_item")
        return _parse_text_subkey(raw, item_type) if isinstance(raw, dict) else None

    if item_type == ItemType.IMAGE:
        raw = item_data.get("image_item")
        return _parse_image_subkey(raw, item_type) if isinstance(raw, dict) else None

    if item_type == ItemType.VOICE:
        raw = item_data.get("voice_item")
        return _parse_voice_subkey(raw, item_type) if isinstance(raw, dict) else None

    if item_type == ItemType.FILE:
        raw = item_data.get("file_item")
        return _parse_file_subkey(raw, item_type) if isinstance(raw, dict) else None

    if item_type == ItemType.VIDEO:
        raw = item_data.get("video_item")
        return _parse_video_subkey(raw, item_type) if isinstance(raw, dict) else None

    return None


# ── Individual sub-key parsers ────────────────────────────────────────


def _parse_text_subkey(data: dict[str, object], effective_type: int) -> MessageItem | None:
    text = data.get("text", "")
    if isinstance(text, str) and text:
        return MessageItem(type=effective_type, text_item=TextItem(text=text))
    return None


def _parse_image_subkey(data: dict[str, object], effective_type: int) -> MessageItem | None:
    url = data.get("url")
    media = parse_media_info(data.get("media"))
    if isinstance(url, str) or media:
        return MessageItem(
            type=effective_type,
            image_item=ImageItem(
                url=url if isinstance(url, str) else None,
                media=media,
                mid_size=int(data["mid_size"]) if isinstance(data.get("mid_size"), int) else None,
            ),
        )
    return None


def _parse_voice_subkey(data: dict[str, object], effective_type: int) -> MessageItem | None:
    media = parse_media_info(data.get("media"))
    text = data.get("text")
    if media or isinstance(text, str):
        return MessageItem(
            type=effective_type,
            voice_item=VoiceItem(
                media=media,
                encode_type=int(data["encode_type"]) if isinstance(data.get("encode_type"), int) else None,
                sample_rate=int(data["sample_rate"]) if isinstance(data.get("sample_rate"), int) else None,
                playtime=int(data["playtime"]) if isinstance(data.get("playtime"), int) else None,
                text=text if isinstance(text, str) else None,
            ),
        )
    return None


def _parse_file_subkey(data: dict[str, object], effective_type: int) -> MessageItem | None:
    media = parse_media_info(data.get("media"))
    if media:
        return MessageItem(
            type=effective_type,
            file_item=FileItem(
                media=media,
                file_name=data["file_name"] if isinstance(data.get("file_name"), str) else None,
                file_size=data["len"] if isinstance(data.get("len"), str) else None,
            ),
        )
    return None


def _parse_video_subkey(data: dict[str, object], effective_type: int) -> MessageItem | None:
    media = parse_media_info(data.get("media"))
    if media:
        return MessageItem(
            type=effective_type,
            video_item=VideoItem(
                media=media,
                video_size=int(data["video_size"]) if isinstance(data.get("video_size"), int) else None,
                play_length=int(data["play_length"]) if isinstance(data.get("play_length"), int) else None,
            ),
        )
    return None


# ── Fallback lookup table (must follow parser definitions) ────────────

_SubKeyParser = Callable[[dict[str, object], int], MessageItem | None]

_SUBKEY_PARSERS: tuple[tuple[str, int, _SubKeyParser], ...] = (
    ("text_item", ItemType.TEXT, _parse_text_subkey),
    ("image_item", ItemType.IMAGE, _parse_image_subkey),
    ("voice_item", ItemType.VOICE, _parse_voice_subkey),
    ("file_item", ItemType.FILE, _parse_file_subkey),
    ("video_item", ItemType.VIDEO, _parse_video_subkey),
)
