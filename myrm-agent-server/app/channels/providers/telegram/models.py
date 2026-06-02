"""Pydantic models for Telegram Bot API webhook payloads.

Provides structured, type-safe validation for incoming Telegram updates.
All fields are optional with defaults to handle partial payloads gracefully.
``extra="allow"`` ensures forward compatibility with new Telegram API fields.

[INPUT]
- (none)

[OUTPUT]
- TgUser: Telegram User object (subset of fields used by the channel).
- TgChat: Telegram Chat object.
- TgPhotoSize: Telegram PhotoSize (largest element of the photo array).
- TgDocument: Shared model for voice and audio objects.
- TgVideo: class — Tg Video
- TgLocation: Telegram Location object (latitude/longitude).
- TgVenue: Telegram Venue object (named place with location).

[POS]
Pydantic models for Telegram Bot API webhook payloads.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class TgUser(BaseModel):
    """Telegram User object (subset of fields used by the channel)."""

    model_config = ConfigDict(extra="allow")

    id: int = 0
    username: str | None = None
    first_name: str | None = None


class TgChat(BaseModel):
    """Telegram Chat object."""

    model_config = ConfigDict(extra="allow")

    id: int = 0
    type: str = ""
    title: str | None = None
    is_forum: bool | None = None


class TgPhotoSize(BaseModel):
    """Telegram PhotoSize (largest element of the photo array)."""

    model_config = ConfigDict(extra="allow")

    file_id: str = ""


class TgDocument(BaseModel):
    model_config = ConfigDict(extra="allow")

    file_id: str = ""
    file_name: str | None = None
    mime_type: str = "application/octet-stream"


class TgVideo(BaseModel):
    model_config = ConfigDict(extra="allow")

    file_id: str = ""


class TgVoiceAudio(BaseModel):
    """Shared model for voice and audio objects."""

    model_config = ConfigDict(extra="allow")

    file_id: str = ""
    mime_type: str = "audio/ogg"
    duration: int = 0


class TgSticker(BaseModel):
    """Telegram Sticker object with vision-relevant fields."""

    model_config = ConfigDict(extra="allow")

    file_id: str = ""
    file_unique_id: str = ""
    emoji: str = ""
    set_name: str = ""
    is_animated: bool = False
    is_video: bool = False


class TgEntity(BaseModel):
    """Telegram MessageEntity."""

    model_config = ConfigDict(extra="allow")

    type: str = ""
    offset: int = 0
    length: int = 0
    user: TgUser | None = None


class TgLocation(BaseModel):
    """Telegram Location object (latitude/longitude coordinates)."""

    model_config = ConfigDict(extra="allow")

    latitude: float = 0.0
    longitude: float = 0.0


class TgVenue(BaseModel):
    """Telegram Venue object (named place with location)."""

    model_config = ConfigDict(extra="allow")

    location: TgLocation = Field(default_factory=TgLocation)
    title: str = ""
    address: str = ""
    foursquare_id: str | None = None


class TgMessage(BaseModel):
    """Telegram Message object (subset of fields used by the channel)."""

    model_config = ConfigDict(extra="allow")

    message_id: int = 0
    from_user: TgUser | None = Field(default=None, alias="from")
    chat: TgChat | None = None
    text: str | None = None
    caption: str | None = None
    photo: list[TgPhotoSize] | None = None
    document: TgDocument | None = None
    video: TgVideo | None = None
    voice: TgVoiceAudio | None = None
    audio: TgVoiceAudio | None = None
    sticker: TgSticker | None = None
    location: TgLocation | None = None
    venue: TgVenue | None = None
    entities: list[TgEntity] | None = None
    caption_entities: list[TgEntity] | None = None
    reply_to_message: TgMessage | None = None
    message_thread_id: int | None = None
    media_group_id: str | None = None


class TgCallbackQuery(BaseModel):
    """Telegram CallbackQuery object."""

    model_config = ConfigDict(extra="allow")

    id: str = ""
    from_user: TgUser | None = Field(default=None, alias="from")
    data: str = ""
    message: TgMessage | None = None


class TgReactionType(BaseModel):
    """Telegram ReactionType — emoji or custom_emoji."""

    model_config = ConfigDict(extra="allow")

    type: str = ""
    emoji: str = ""


class TgMessageReactionUpdated(BaseModel):
    """Telegram MessageReactionUpdated (Bot API 7.0+)."""

    model_config = ConfigDict(extra="allow")

    chat: TgChat | None = None
    message_id: int = 0
    user: TgUser | None = None
    date: int = 0
    new_reaction: list[TgReactionType] = Field(default_factory=list)


class TgUpdate(BaseModel):
    """Top-level Telegram Update object received via webhook or getUpdates."""

    model_config = ConfigDict(extra="allow")

    update_id: int = 0
    message: TgMessage | None = None
    edited_message: TgMessage | None = None
    callback_query: TgCallbackQuery | None = None
    message_reaction: TgMessageReactionUpdated | None = None
