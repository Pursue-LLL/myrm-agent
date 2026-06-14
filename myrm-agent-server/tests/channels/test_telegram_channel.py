"""TelegramChannel contract + inbound parsing + API client + outbound tests."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.channels.core.base import BaseChannel, ChannelStatus
from app.channels.providers.telegram import TelegramChannel
from app.channels.providers.telegram.api import (
    TelegramApiError,
    TelegramClient,
)
from app.channels.providers.telegram.models import (
    TgMessage,
    TgUpdate,
)
from app.channels.types import (
    METADATA_EXPLICIT_MENTION_KEY,
    MediaAttachment,
    MediaType,
    OutboundMessage,
)

from .channel_test_base import FAKE_TELEGRAM_BOT_TOKEN, ChannelTestBase


def _make_channel() -> TelegramChannel:
    ch = TelegramChannel(bot_token=FAKE_TELEGRAM_BOT_TOKEN)
    ch._bot_username = "testbot"
    ch._tg_bot_id = 123456789
    ch._rich_send_available = False
    ch._rich_draft_available = False
    return ch


class TestTelegramChannel(ChannelTestBase):
    def create_channel(self) -> BaseChannel:
        return TelegramChannel(bot_token=FAKE_TELEGRAM_BOT_TOKEN)


class TestTgModels:
    """Pydantic model validation tests."""

    def test_update_from_dict(self) -> None:
        raw = {
            "update_id": 100,
            "message": {
                "message_id": 1,
                "from": {"id": 42, "username": "alice"},
                "chat": {"id": -100, "type": "private"},
                "text": "hello",
            },
        }
        tg = TgUpdate.model_validate(raw)
        assert tg.update_id == 100
        assert tg.message is not None
        assert tg.message.from_user is not None
        assert tg.message.from_user.id == 42
        assert tg.message.from_user.username == "alice"
        assert tg.message.chat is not None
        assert tg.message.chat.id == -100

    def test_update_callback_query(self) -> None:
        raw = {
            "update_id": 200,
            "callback_query": {
                "id": "cbq_1",
                "from": {"id": 42},
                "data": "qr:hello",
                "message": {"message_id": 5, "chat": {"id": -100, "type": "group"}},
            },
        }
        tg = TgUpdate.model_validate(raw)
        assert tg.callback_query is not None
        assert tg.callback_query.id == "cbq_1"
        assert tg.callback_query.data == "qr:hello"

    def test_update_extra_fields_allowed(self) -> None:
        raw = {"update_id": 1, "unknown_field": "value"}
        tg = TgUpdate.model_validate(raw)
        assert tg.update_id == 1

    def test_message_with_media(self) -> None:
        raw = {
            "message_id": 10,
            "from": {"id": 42},
            "chat": {"id": -100, "type": "private"},
            "photo": [{"file_id": "small"}, {"file_id": "large"}],
            "caption": "a photo",
        }
        msg = TgMessage.model_validate(raw)
        assert msg.photo is not None
        assert len(msg.photo) == 2
        assert msg.photo[-1].file_id == "large"
        assert msg.caption == "a photo"

    def test_message_with_sticker(self) -> None:
        raw = {
            "message_id": 11,
            "from": {"id": 42},
            "chat": {"id": -100, "type": "private"},
            "sticker": {"file_id": "stk_1", "emoji": "\U0001f60a"},
        }
        msg = TgMessage.model_validate(raw)
        assert msg.sticker is not None
        assert msg.sticker.emoji == "\U0001f60a"

    def test_message_with_location(self) -> None:
        raw = {
            "message_id": 12,
            "from": {"id": 42},
            "chat": {"id": -100, "type": "private"},
            "location": {"latitude": 39.9042, "longitude": 116.4074},
        }
        msg = TgMessage.model_validate(raw)
        assert msg.location is not None
        assert msg.location.latitude == pytest.approx(39.9042)
        assert msg.location.longitude == pytest.approx(116.4074)

    def test_message_with_venue(self) -> None:
        raw = {
            "message_id": 13,
            "from": {"id": 42},
            "chat": {"id": -100, "type": "private"},
            "venue": {
                "location": {"latitude": 40.35, "longitude": 116.00},
                "title": "Great Wall",
                "address": "Badaling",
                "foursquare_id": "4bf58dd8d48988d1e0931735",
            },
        }
        msg = TgMessage.model_validate(raw)
        assert msg.venue is not None
        assert msg.venue.title == "Great Wall"
        assert msg.venue.address == "Badaling"
        assert msg.venue.foursquare_id == "4bf58dd8d48988d1e0931735"
        assert msg.venue.location.latitude == pytest.approx(40.35)


class TestParseUpdate:
    """Test TelegramInboundMixin._parse_update with Pydantic models."""

    def test_text_message(self) -> None:
        ch = _make_channel()
        raw = {
            "update_id": 1,
            "message": {
                "message_id": 10,
                "from": {"id": 42, "username": "alice", "first_name": "Alice"},
                "chat": {"id": 42, "type": "private"},
                "text": "hello world",
            },
        }
        msg = ch._parse_update(raw)
        assert msg is not None
        assert msg.content == "hello world"
        assert msg.sender_id == "42"
        assert msg.chat_id == "42"
        assert msg.is_group is False

    def test_empty_text_no_media_returns_none(self) -> None:
        ch = _make_channel()
        raw = {
            "update_id": 2,
            "message": {
                "message_id": 11,
                "from": {"id": 42},
                "chat": {"id": 42, "type": "private"},
                "text": "   ",
            },
        }
        assert ch._parse_update(raw) is None

    def test_no_message_returns_none(self) -> None:
        ch = _make_channel()
        assert ch._parse_update({"update_id": 3}) is None

    def test_no_from_returns_none(self) -> None:
        ch = _make_channel()
        raw = {
            "update_id": 4,
            "message": {
                "message_id": 12,
                "chat": {"id": 42, "type": "private"},
                "text": "hello",
            },
        }
        assert ch._parse_update(raw) is None

    def test_edited_message(self) -> None:
        ch = _make_channel()
        raw = {
            "update_id": 5,
            "edited_message": {
                "message_id": 13,
                "from": {"id": 42, "username": "alice"},
                "chat": {"id": 42, "type": "private"},
                "text": "edited text",
            },
        }
        msg = ch._parse_update(raw)
        assert msg is not None
        assert msg.content == "edited text"
        assert msg.metadata.get("is_edit") is True

    def test_photo_message(self) -> None:
        ch = _make_channel()
        raw = {
            "update_id": 6,
            "message": {
                "message_id": 14,
                "from": {"id": 42},
                "chat": {"id": 42, "type": "private"},
                "photo": [{"file_id": "small"}, {"file_id": "large"}],
                "caption": "a photo",
            },
        }
        msg = ch._parse_update(raw)
        assert msg is not None
        assert msg.content == "a photo"
        assert len(msg.media) == 1
        assert msg.media[0].media_type == MediaType.IMAGE
        assert msg.metadata.get("photo_file_id") == "large"

    def test_document_message(self) -> None:
        ch = _make_channel()
        raw = {
            "update_id": 7,
            "message": {
                "message_id": 15,
                "from": {"id": 42},
                "chat": {"id": 42, "type": "private"},
                "document": {
                    "file_id": "doc_1",
                    "file_name": "report.pdf",
                    "mime_type": "application/pdf",
                },
            },
        }
        msg = ch._parse_update(raw)
        assert msg is not None
        assert len(msg.media) == 1
        assert msg.media[0].media_type == MediaType.DOCUMENT
        assert msg.media[0].filename == "report.pdf"
        assert msg.media[0].mime_type == "application/pdf"

    def test_voice_message(self) -> None:
        ch = _make_channel()
        raw = {
            "update_id": 8,
            "message": {
                "message_id": 16,
                "from": {"id": 42},
                "chat": {"id": 42, "type": "private"},
                "voice": {"file_id": "voice_1", "duration": 5, "mime_type": "audio/ogg"},
            },
        }
        msg = ch._parse_update(raw)
        assert msg is not None
        assert len(msg.media) == 1
        assert msg.media[0].media_type == MediaType.AUDIO
        assert msg.metadata.get("voice_is_voice_note") is True
        assert msg.metadata.get("voice_duration") == 5

    def test_video_message(self) -> None:
        ch = _make_channel()
        raw = {
            "update_id": 9,
            "message": {
                "message_id": 17,
                "from": {"id": 42},
                "chat": {"id": 42, "type": "private"},
                "video": {"file_id": "vid_1"},
                "caption": "a video",
            },
        }
        msg = ch._parse_update(raw)
        assert msg is not None
        assert len(msg.media) == 1
        assert msg.media[0].media_type == MediaType.VIDEO

    def test_sticker_message(self) -> None:
        ch = _make_channel()
        raw = {
            "update_id": 10,
            "message": {
                "message_id": 18,
                "from": {"id": 42},
                "chat": {"id": 42, "type": "private"},
                "sticker": {"file_id": "stk_1", "emoji": "\U0001f60a"},
            },
        }
        msg = ch._parse_update(raw)
        assert msg is not None
        assert msg.content == "\U0001f60a"
        assert msg.metadata.get("is_sticker") is True

    def test_group_message_with_mention(self) -> None:
        ch = _make_channel()
        raw = {
            "update_id": 11,
            "message": {
                "message_id": 19,
                "from": {"id": 42},
                "chat": {"id": -100, "type": "supergroup"},
                "text": "@testbot hello",
                "entities": [{"type": "mention", "offset": 0, "length": 8}],
            },
        }
        msg = ch._parse_update(raw)
        assert msg is not None
        assert msg.is_group is True
        assert msg.mentioned is True
        assert msg.metadata.get(METADATA_EXPLICIT_MENTION_KEY) == "1"
        assert msg.content == "hello"

    def test_group_message_text_mention(self) -> None:
        ch = _make_channel()
        raw = {
            "update_id": 12,
            "message": {
                "message_id": 20,
                "from": {"id": 42},
                "chat": {"id": -100, "type": "group"},
                "text": "Bot hello",
                "entities": [{"type": "text_mention", "offset": 0, "length": 3, "user": {"id": 123456789}}],
            },
        }
        msg = ch._parse_update(raw)
        assert msg is not None
        assert msg.mentioned is True
        assert msg.metadata.get(METADATA_EXPLICIT_MENTION_KEY) == "1"

    def test_group_message_caption_mention(self) -> None:
        ch = _make_channel()
        raw = {
            "update_id": 12,
            "message": {
                "message_id": 21,
                "from": {"id": 42},
                "chat": {"id": -100, "type": "supergroup"},
                "photo": [{"file_id": "photo_1", "width": 100, "height": 100}],
                "caption": "@testbot what is this?",
                "caption_entities": [{"type": "mention", "offset": 0, "length": 8}],
            },
        }
        msg = ch._parse_update(raw)
        assert msg is not None
        assert msg.mentioned is True
        assert msg.metadata.get(METADATA_EXPLICIT_MENTION_KEY) == "1"
        assert msg.content == "what is this?"

    def test_group_message_bot_command_entity(self) -> None:
        ch = _make_channel()
        raw = {
            "update_id": 12,
            "message": {
                "message_id": 22,
                "from": {"id": 42},
                "chat": {"id": -100, "type": "group"},
                "text": "/status@testbot",
                "entities": [{"type": "bot_command", "offset": 0, "length": 15}],
            },
        }
        msg = ch._parse_update(raw)
        assert msg is not None
        assert msg.mentioned is True
        assert msg.metadata.get(METADATA_EXPLICIT_MENTION_KEY) == "1"
        assert msg.content == "/status"

    def test_edited_message_caption_mention(self) -> None:
        ch = _make_channel()
        raw = {
            "update_id": 14,
            "edited_message": {
                "message_id": 23,
                "from": {"id": 42},
                "chat": {"id": -100, "type": "group"},
                "photo": [{"file_id": "photo_2", "width": 100, "height": 100}],
                "caption": "@testbot updated caption",
                "caption_entities": [{"type": "mention", "offset": 0, "length": 8}],
            },
        }
        msg = ch._parse_update(raw)
        assert msg is not None
        assert msg.mentioned is True
        assert msg.metadata.get("is_edit") is True
        assert msg.metadata.get(METADATA_EXPLICIT_MENTION_KEY) == "1"
        assert msg.content == "updated caption"

    def test_reply_to_bot_implies_mentioned(self) -> None:
        ch = _make_channel()
        raw = {
            "update_id": 13,
            "message": {
                "message_id": 21,
                "from": {"id": 42},
                "chat": {"id": -100, "type": "group"},
                "text": "reply text",
                "reply_to_message": {
                    "message_id": 20,
                    "from": {"id": 123456789},
                    "chat": {"id": -100, "type": "group"},
                    "text": "bot message",
                },
            },
        }
        msg = ch._parse_update(raw)
        assert msg is not None
        assert msg.mentioned is True
        assert msg.metadata.get(METADATA_EXPLICIT_MENTION_KEY) is None
        assert msg.reply_to_id == "20"

    def test_reply_to_caption_message(self) -> None:
        ch = _make_channel()
        raw = {
            "update_id": 24,
            "message": {
                "message_id": 36,
                "from": {"id": 42},
                "chat": {"id": 42, "type": "private"},
                "text": "what is this?",
                "reply_to_message": {
                    "message_id": 35,
                    "from": {"id": 99, "first_name": "Bob"},
                    "chat": {"id": 42, "type": "private"},
                    "caption": "sunset photo",
                    "photo": [{"file_id": "p1"}],
                },
            },
        }
        msg = ch._parse_update(raw)
        assert msg is not None
        assert msg.reply_to is not None
        assert msg.reply_to.content == "sunset photo"
        assert len(msg.reply_to.media) == 1
        assert msg.reply_to.media[0].media_type == MediaType.IMAGE
        assert msg.reply_to.sender_name == "Bob"

    def test_reply_to_document_message(self) -> None:
        ch = _make_channel()
        raw = {
            "update_id": 25,
            "message": {
                "message_id": 37,
                "from": {"id": 42},
                "chat": {"id": 42, "type": "private"},
                "text": "check this",
                "reply_to_message": {
                    "message_id": 36,
                    "from": {"id": 99},
                    "chat": {"id": 42, "type": "private"},
                    "document": {"file_id": "doc1", "mime_type": "application/pdf", "file_name": "report.pdf"},
                },
            },
        }
        msg = ch._parse_update(raw)
        assert msg is not None
        assert msg.reply_to is not None
        assert len(msg.reply_to.media) == 1
        assert msg.reply_to.media[0].media_type == MediaType.DOCUMENT
        assert msg.reply_to.media[0].mime_type == "application/pdf"

    def test_reply_to_video_message(self) -> None:
        ch = _make_channel()
        raw = {
            "update_id": 26,
            "message": {
                "message_id": 38,
                "from": {"id": 42},
                "chat": {"id": 42, "type": "private"},
                "text": "nice video",
                "reply_to_message": {
                    "message_id": 37,
                    "from": {"id": 99},
                    "chat": {"id": 42, "type": "private"},
                    "video": {"file_id": "vid1"},
                    "caption": "my video",
                },
            },
        }
        msg = ch._parse_update(raw)
        assert msg is not None
        assert msg.reply_to is not None
        assert msg.reply_to.content == "my video"
        assert len(msg.reply_to.media) == 1
        assert msg.reply_to.media[0].media_type == MediaType.VIDEO

    def test_reply_to_voice_message(self) -> None:
        ch = _make_channel()
        raw = {
            "update_id": 27,
            "message": {
                "message_id": 39,
                "from": {"id": 42},
                "chat": {"id": 42, "type": "private"},
                "text": "what did you say?",
                "reply_to_message": {
                    "message_id": 38,
                    "from": {"id": 99},
                    "chat": {"id": 42, "type": "private"},
                    "voice": {"file_id": "v1", "duration": 5, "mime_type": "audio/ogg"},
                },
            },
        }
        msg = ch._parse_update(raw)
        assert msg is not None
        assert msg.reply_to is not None
        assert len(msg.reply_to.media) == 1
        assert msg.reply_to.media[0].media_type == MediaType.AUDIO

    def test_reply_to_sticker_message(self) -> None:
        ch = _make_channel()
        raw = {
            "update_id": 28,
            "message": {
                "message_id": 40,
                "from": {"id": 42},
                "chat": {"id": 42, "type": "private"},
                "text": "funny",
                "reply_to_message": {
                    "message_id": 39,
                    "from": {"id": 99},
                    "chat": {"id": 42, "type": "private"},
                    "sticker": {"file_id": "stk1", "emoji": "\U0001f602"},
                },
            },
        }
        msg = ch._parse_update(raw)
        assert msg is not None
        assert msg.reply_to is not None
        assert msg.reply_to.content == "\U0001f602"
        assert len(msg.reply_to.media) == 1
        assert msg.reply_to.media[0].media_type == MediaType.IMAGE

    def test_reply_to_empty_returns_none(self) -> None:
        ch = _make_channel()
        raw = {
            "update_id": 29,
            "message": {
                "message_id": 41,
                "from": {"id": 42},
                "chat": {"id": 42, "type": "private"},
                "text": "hmm",
                "reply_to_message": {
                    "message_id": 40,
                    "chat": {"id": 42, "type": "private"},
                },
            },
        }
        msg = ch._parse_update(raw)
        assert msg is not None
        assert msg.reply_to is None

    def test_thread_id_parsed(self) -> None:
        ch = _make_channel()
        raw = {
            "update_id": 14,
            "message": {
                "message_id": 22,
                "from": {"id": 42},
                "chat": {"id": -100, "type": "supergroup", "is_forum": True},
                "text": "forum message",
                "message_thread_id": 999,
            },
        }
        msg = ch._parse_update(raw)
        assert msg is not None
        assert msg.thread_id == "999"
        assert msg.metadata.get("is_forum") is True

    @pytest.mark.asyncio
    async def test_callback_query(self) -> None:
        ch = _make_channel()
        ch._client = MagicMock()
        ch._client.answer_callback_query = AsyncMock()
        ch._background_tasks = set()
        raw = {
            "update_id": 15,
            "callback_query": {
                "id": "cbq_1",
                "from": {"id": 42, "username": "alice"},
                "data": "qr:hello",
                "message": {
                    "message_id": 5,
                    "chat": {"id": -100, "type": "group"},
                },
            },
        }
        msg = ch._parse_update(raw)
        assert msg is not None
        assert msg.content == "hello"
        assert msg.metadata.get("callback_prefix") == "qr"

    @pytest.mark.asyncio
    async def test_callback_query_invalid_prefix(self) -> None:
        ch = _make_channel()
        ch._client = MagicMock()
        ch._background_tasks = set()
        raw = {
            "update_id": 16,
            "callback_query": {
                "id": "cbq_2",
                "from": {"id": 42},
                "data": "unknown:value",
            },
        }
        assert ch._parse_update(raw) is None

    @pytest.mark.asyncio
    async def test_callback_query_no_colon(self) -> None:
        ch = _make_channel()
        ch._client = MagicMock()
        ch._background_tasks = set()
        raw = {
            "update_id": 17,
            "callback_query": {
                "id": "cbq_3",
                "from": {"id": 42},
                "data": "nocolon",
            },
        }
        assert ch._parse_update(raw) is None

    def test_invalid_payload_returns_none(self) -> None:
        """Completely invalid payload should be handled gracefully."""
        ch = _make_channel()
        assert ch._parse_update({}) is None

    def test_audio_message(self) -> None:
        ch = _make_channel()
        raw = {
            "update_id": 18,
            "message": {
                "message_id": 30,
                "from": {"id": 42},
                "chat": {"id": 42, "type": "private"},
                "audio": {"file_id": "audio_1", "duration": 120, "mime_type": "audio/mp3"},
            },
        }
        msg = ch._parse_update(raw)
        assert msg is not None
        assert len(msg.media) == 1
        assert msg.media[0].media_type == MediaType.AUDIO
        assert msg.metadata.get("voice_is_voice_note") is False

    def test_location_message(self) -> None:
        ch = _make_channel()
        raw = {
            "update_id": 19,
            "message": {
                "message_id": 31,
                "from": {"id": 42, "username": "alice"},
                "chat": {"id": 42, "type": "private"},
                "location": {"latitude": 39.9042, "longitude": 116.4074},
            },
        }
        msg = ch._parse_update(raw)
        assert msg is not None
        assert "39.9042,116.4074" in msg.content
        assert "google.com/maps" in msg.content
        assert msg.content.startswith("[Location:")

    def test_venue_message(self) -> None:
        ch = _make_channel()
        raw = {
            "update_id": 20,
            "message": {
                "message_id": 32,
                "from": {"id": 42, "username": "alice"},
                "chat": {"id": 42, "type": "private"},
                "venue": {
                    "location": {"latitude": 40.35, "longitude": 116.00},
                    "title": "The Great Wall",
                    "address": "Badaling, Beijing",
                },
            },
        }
        msg = ch._parse_update(raw)
        assert msg is not None
        assert "The Great Wall" in msg.content
        assert "Badaling, Beijing" in msg.content
        assert "40.35,116.0" in msg.content
        assert "google.com/maps" in msg.content
        assert msg.content.startswith("[Venue:")

    def test_venue_without_address(self) -> None:
        ch = _make_channel()
        raw = {
            "update_id": 21,
            "message": {
                "message_id": 33,
                "from": {"id": 42},
                "chat": {"id": 42, "type": "private"},
                "venue": {
                    "location": {"latitude": 31.23, "longitude": 121.47},
                    "title": "Some Place",
                    "address": "",
                },
            },
        }
        msg = ch._parse_update(raw)
        assert msg is not None
        assert "Some Place" in msg.content
        assert "Address:" not in msg.content

    def test_venue_takes_priority_over_location(self) -> None:
        """When both venue and location are present, venue wins (richer info)."""
        ch = _make_channel()
        raw = {
            "update_id": 22,
            "message": {
                "message_id": 34,
                "from": {"id": 42},
                "chat": {"id": 42, "type": "private"},
                "venue": {
                    "location": {"latitude": 48.86, "longitude": 2.35},
                    "title": "Eiffel Tower",
                    "address": "Paris, France",
                },
                "location": {"latitude": 48.86, "longitude": 2.35},
            },
        }
        msg = ch._parse_update(raw)
        assert msg is not None
        assert msg.content.startswith("[Venue:")
        assert "Eiffel Tower" in msg.content

    def test_location_southern_hemisphere(self) -> None:
        """Negative coordinates (southern/western hemisphere) should work correctly."""
        ch = _make_channel()
        raw = {
            "update_id": 30,
            "message": {
                "message_id": 42,
                "from": {"id": 42},
                "chat": {"id": 42, "type": "private"},
                "location": {"latitude": -33.8688, "longitude": 151.2093},
            },
        }
        msg = ch._parse_update(raw)
        assert msg is not None
        assert "-33.8688,151.2093" in msg.content
        assert msg.content.startswith("[Location:")

    def test_text_not_overridden_by_location(self) -> None:
        """If both text and location exist, text takes priority (defensive)."""
        ch = _make_channel()
        raw = {
            "update_id": 31,
            "message": {
                "message_id": 43,
                "from": {"id": 42},
                "chat": {"id": 42, "type": "private"},
                "text": "Find restaurants near me",
                "location": {"latitude": 39.9, "longitude": 116.4},
            },
        }
        msg = ch._parse_update(raw)
        assert msg is not None
        assert msg.content == "Find restaurants near me"
        assert "[Location:" not in msg.content

    def test_location_in_group_with_mention(self) -> None:
        ch = _make_channel()
        raw = {
            "update_id": 23,
            "message": {
                "message_id": 35,
                "from": {"id": 42, "username": "alice"},
                "chat": {"id": -100, "type": "supergroup"},
                "location": {"latitude": 35.68, "longitude": 139.69},
            },
        }
        msg = ch._parse_update(raw)
        assert msg is not None
        assert msg.is_group is True
        assert "35.68,139.69" in msg.content

    def test_message_reaction_emoji(self) -> None:
        ch = _make_channel()
        raw = {
            "update_id": 50,
            "message_reaction": {
                "chat": {"id": -100, "type": "supergroup"},
                "message_id": 42,
                "user": {"id": 99, "username": "bob"},
                "date": 1700000000,
                "new_reaction": [{"type": "emoji", "emoji": "\U0001f44d"}],
            },
        }
        msg = ch._parse_update(raw)
        assert msg is not None
        assert msg.content == "\U0001f44d"
        assert msg.sender_id == "99"
        assert msg.chat_id == "-100"
        assert msg.is_group is True
        assert msg.message_id == "42"
        assert msg.metadata.get("reaction") is True
        assert msg.metadata.get("target_message_id") == "42"

    def test_message_reaction_private_chat(self) -> None:
        ch = _make_channel()
        raw = {
            "update_id": 51,
            "message_reaction": {
                "chat": {"id": 42, "type": "private"},
                "message_id": 10,
                "user": {"id": 42, "username": "alice"},
                "date": 1700000000,
                "new_reaction": [{"type": "emoji", "emoji": "\u2764\ufe0f"}],
            },
        }
        msg = ch._parse_update(raw)
        assert msg is not None
        assert msg.content == "\u2764\ufe0f"
        assert msg.is_group is False

    def test_message_reaction_no_user_returns_none(self) -> None:
        ch = _make_channel()
        raw = {
            "update_id": 52,
            "message_reaction": {
                "chat": {"id": -100, "type": "group"},
                "message_id": 42,
                "user": None,
                "date": 1700000000,
                "new_reaction": [{"type": "emoji", "emoji": "\U0001f44d"}],
            },
        }
        assert ch._parse_update(raw) is None

    def test_message_reaction_no_emoji_returns_none(self) -> None:
        ch = _make_channel()
        raw = {
            "update_id": 53,
            "message_reaction": {
                "chat": {"id": -100, "type": "group"},
                "message_id": 42,
                "user": {"id": 99},
                "date": 1700000000,
                "new_reaction": [{"type": "custom_emoji", "custom_emoji_id": "xyz"}],
            },
        }
        assert ch._parse_update(raw) is None

    def test_message_reaction_empty_reactions_returns_none(self) -> None:
        ch = _make_channel()
        raw = {
            "update_id": 54,
            "message_reaction": {
                "chat": {"id": -100, "type": "group"},
                "message_id": 42,
                "user": {"id": 99},
                "date": 1700000000,
                "new_reaction": [],
            },
        }
        assert ch._parse_update(raw) is None

    def test_message_reaction_multiple_picks_first_emoji(self) -> None:
        """When multiple reactions exist, first emoji type is used."""
        ch = _make_channel()
        raw = {
            "update_id": 55,
            "message_reaction": {
                "chat": {"id": 42, "type": "private"},
                "message_id": 7,
                "user": {"id": 99},
                "date": 1700000000,
                "new_reaction": [
                    {"type": "emoji", "emoji": "\u2764\ufe0f"},
                    {"type": "emoji", "emoji": "\U0001f44d"},
                ],
            },
        }
        msg = ch._parse_update(raw)
        assert msg is not None
        assert msg.content == "\u2764\ufe0f"


class TestBufferOrEmit:
    @pytest.mark.asyncio
    async def test_non_media_group_emits_directly(self) -> None:
        ch = _make_channel()
        received = []

        async def handler(msg):
            received.append(msg)

        ch.set_inbound_handler(handler)
        ch._status = "running"

        raw = {
            "update_id": 1,
            "message": {
                "message_id": 10,
                "from": {"id": 42},
                "chat": {"id": 42, "type": "private"},
                "text": "hello",
            },
        }
        msg = ch._parse_update(raw)
        assert msg is not None
        await ch._buffer_or_emit(msg, raw)
        assert len(received) == 1

    @pytest.mark.asyncio
    async def test_media_group_buffers(self) -> None:
        ch = _make_channel()
        received = []

        async def handler(msg):
            received.append(msg)

        ch.set_inbound_handler(handler)
        ch._status = "running"

        raw = {
            "update_id": 1,
            "message": {
                "message_id": 10,
                "from": {"id": 42},
                "chat": {"id": 42, "type": "private"},
                "photo": [{"file_id": "p1"}],
                "caption": "photo 1",
                "media_group_id": "mg_1",
            },
        }
        msg = ch._parse_update(raw)
        assert msg is not None
        await ch._buffer_or_emit(msg, raw)
        assert "42:mg_1" in ch._mg_buffers


# ── TelegramApiError Tests ───────────────────────────────────


class TestTelegramApiError:
    def test_basic_error(self) -> None:
        err = TelegramApiError(400, "Bad Request")
        assert err.error_code == 400
        assert err.description == "Bad Request"
        assert str(err) == "Telegram API 400: Bad Request"

    def test_is_parse_error(self) -> None:
        err = TelegramApiError(400, "Bad Request: can't parse entities")
        assert err.is_parse_error is True
        err2 = TelegramApiError(400, "Bad Request: other")
        assert err2.is_parse_error is False

    def test_is_not_modified(self) -> None:
        err = TelegramApiError(400, "Bad Request: message is not modified")
        assert err.is_not_modified is True

    def test_parameters(self) -> None:
        err = TelegramApiError(429, "Too Many Requests", {"retry_after": 30})
        assert err.parameters.get("retry_after") == 30


# ── TelegramClient Tests ─────────────────────────────────────


class TestTelegramClient:
    def _make_client(self, api_base: str | None = None) -> TelegramClient:
        return TelegramClient(FAKE_TELEGRAM_BOT_TOKEN, api_base=api_base)

    def test_custom_api_base(self) -> None:
        client = self._make_client(api_base="https://custom.api.org")
        assert "custom.api.org" in client._base

    def test_default_api_base(self) -> None:
        client = self._make_client()
        assert "api.telegram.org" in client._base

    def test_token_property(self) -> None:
        client = self._make_client()
        assert client.token == FAKE_TELEGRAM_BOT_TOKEN

    @pytest.mark.asyncio
    async def test_call_success(self) -> None:
        client = self._make_client()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"ok": True, "result": {"id": 123, "username": "bot"}}
        mock_http = MagicMock()
        mock_http.post = AsyncMock(return_value=mock_resp)
        mock_http.is_closed = False
        client._http = mock_http

        result = await client.get_me()
        assert result["id"] == 123

    @pytest.mark.asyncio
    async def test_call_api_error(self) -> None:
        client = self._make_client()
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_resp.json.return_value = {"ok": False, "error_code": 401, "description": "Unauthorized"}
        mock_http = MagicMock()
        mock_http.post = AsyncMock(return_value=mock_resp)
        mock_http.is_closed = False
        client._http = mock_http

        with pytest.raises(TelegramApiError) as exc_info:
            await client.get_me()
        assert exc_info.value.error_code == 401

    @pytest.mark.asyncio
    async def test_verify_token_success(self) -> None:
        client = self._make_client()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"ok": True, "result": {"id": 1}}
        mock_http = MagicMock()
        mock_http.post = AsyncMock(return_value=mock_resp)
        mock_http.is_closed = False
        client._http = mock_http

        assert await client.verify_token() is True

    @pytest.mark.asyncio
    async def test_verify_token_failure(self) -> None:
        client = self._make_client()
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_resp.json.return_value = {"ok": False, "error_code": 401, "description": "Unauthorized"}
        mock_http = MagicMock()
        mock_http.post = AsyncMock(return_value=mock_resp)
        mock_http.is_closed = False
        client._http = mock_http

        assert await client.verify_token() is False

    @pytest.mark.asyncio
    async def test_get_updates(self) -> None:
        client = self._make_client()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"ok": True, "result": [{"update_id": 1}]}
        mock_http = MagicMock()
        mock_http.post = AsyncMock(return_value=mock_resp)
        mock_http.is_closed = False
        client._http = mock_http

        updates = await client.get_updates(offset=0)
        assert len(updates) == 1

    @pytest.mark.asyncio
    async def test_send_message(self) -> None:
        client = self._make_client()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"ok": True, "result": {"message_id": 42}}
        mock_http = MagicMock()
        mock_http.post = AsyncMock(return_value=mock_resp)
        mock_http.is_closed = False
        client._http = mock_http

        result = await client.send_message(123, "Hello!")
        assert result["message_id"] == 42

    @pytest.mark.asyncio
    async def test_send_message_with_reply(self) -> None:
        client = self._make_client()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"ok": True, "result": {"message_id": 43}}
        mock_http = MagicMock()
        mock_http.post = AsyncMock(return_value=mock_resp)
        mock_http.is_closed = False
        client._http = mock_http

        result = await client.send_message(123, "Reply", reply_to_message_id=10)
        assert result["message_id"] == 43
        call_json = mock_http.post.call_args.kwargs.get("json")
        assert "reply_parameters" in call_json

    @pytest.mark.asyncio
    async def test_edit_message_text(self) -> None:
        client = self._make_client()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"ok": True, "result": {"message_id": 42}}
        mock_http = MagicMock()
        mock_http.post = AsyncMock(return_value=mock_resp)
        mock_http.is_closed = False
        client._http = mock_http

        result = await client.edit_message_text(123, 42, "Updated")
        assert result["message_id"] == 42

    @pytest.mark.asyncio
    async def test_delete_message(self) -> None:
        client = self._make_client()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"ok": True, "result": True}
        mock_http = MagicMock()
        mock_http.post = AsyncMock(return_value=mock_resp)
        mock_http.is_closed = False
        client._http = mock_http

        assert await client.delete_message(123, 42) is True

    @pytest.mark.asyncio
    async def test_delete_message_failure(self) -> None:
        client = self._make_client()
        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_resp.json.return_value = {"ok": False, "error_code": 400, "description": "not found"}
        mock_http = MagicMock()
        mock_http.post = AsyncMock(return_value=mock_resp)
        mock_http.is_closed = False
        client._http = mock_http

        assert await client.delete_message(123, 42) is False

    @pytest.mark.asyncio
    async def test_send_photo_url(self) -> None:
        client = self._make_client()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"ok": True, "result": {"message_id": 50}}
        mock_http = MagicMock()
        mock_http.post = AsyncMock(return_value=mock_resp)
        mock_http.is_closed = False
        client._http = mock_http

        result = await client.send_photo(123, "https://example.com/img.jpg")
        assert result["message_id"] == 50

    @pytest.mark.asyncio
    async def test_send_photo_bytes(self) -> None:
        client = self._make_client()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"ok": True, "result": {"message_id": 51}}
        mock_http = MagicMock()
        mock_http.post = AsyncMock(return_value=mock_resp)
        mock_http.is_closed = False
        client._http = mock_http

        result = await client.send_photo(123, b"\x89PNG", caption="Photo")
        assert result["message_id"] == 51

    @pytest.mark.asyncio
    async def test_send_document_url(self) -> None:
        client = self._make_client()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"ok": True, "result": {"message_id": 52}}
        mock_http = MagicMock()
        mock_http.post = AsyncMock(return_value=mock_resp)
        mock_http.is_closed = False
        client._http = mock_http

        result = await client.send_document(123, "https://example.com/doc.pdf")
        assert result["message_id"] == 52

    @pytest.mark.asyncio
    async def test_send_voice_bytes(self) -> None:
        client = self._make_client()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"ok": True, "result": {"message_id": 53}}
        mock_http = MagicMock()
        mock_http.post = AsyncMock(return_value=mock_resp)
        mock_http.is_closed = False
        client._http = mock_http

        result = await client.send_voice(123, b"ogg_data")
        assert result["message_id"] == 53

    @pytest.mark.asyncio
    async def test_send_audio_url(self) -> None:
        client = self._make_client()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"ok": True, "result": {"message_id": 54}}
        mock_http = MagicMock()
        mock_http.post = AsyncMock(return_value=mock_resp)
        mock_http.is_closed = False
        client._http = mock_http

        result = await client.send_audio(123, "https://example.com/a.mp3")
        assert result["message_id"] == 54

    @pytest.mark.asyncio
    async def test_send_video_bytes(self) -> None:
        client = self._make_client()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"ok": True, "result": {"message_id": 55}}
        mock_http = MagicMock()
        mock_http.post = AsyncMock(return_value=mock_resp)
        mock_http.is_closed = False
        client._http = mock_http

        result = await client.send_video(123, b"mp4_data")
        assert result["message_id"] == 55

    @pytest.mark.asyncio
    async def test_send_chat_action(self) -> None:
        client = self._make_client()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"ok": True, "result": True}
        mock_http = MagicMock()
        mock_http.post = AsyncMock(return_value=mock_resp)
        mock_http.is_closed = False
        client._http = mock_http

        await client.send_chat_action(123, "typing")

    @pytest.mark.asyncio
    async def test_set_webhook(self) -> None:
        client = self._make_client()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"ok": True, "result": True}
        mock_http = MagicMock()
        mock_http.post = AsyncMock(return_value=mock_resp)
        mock_http.is_closed = False
        client._http = mock_http

        assert await client.set_webhook("https://example.com/webhook", secret_token="sec") is True

    @pytest.mark.asyncio
    async def test_delete_webhook(self) -> None:
        client = self._make_client()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"ok": True, "result": True}
        mock_http = MagicMock()
        mock_http.post = AsyncMock(return_value=mock_resp)
        mock_http.is_closed = False
        client._http = mock_http

        assert await client.delete_webhook() is True

    @pytest.mark.asyncio
    async def test_set_my_commands(self) -> None:
        client = self._make_client()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"ok": True, "result": True}
        mock_http = MagicMock()
        mock_http.post = AsyncMock(return_value=mock_resp)
        mock_http.is_closed = False
        client._http = mock_http

        assert await client.set_my_commands([{"command": "start", "description": "Start"}]) is True

    @pytest.mark.asyncio
    async def test_answer_callback_query(self) -> None:
        client = self._make_client()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"ok": True, "result": True}
        mock_http = MagicMock()
        mock_http.post = AsyncMock(return_value=mock_resp)
        mock_http.is_closed = False
        client._http = mock_http

        await client.answer_callback_query("cbq_1")

    @pytest.mark.asyncio
    async def test_get_file(self) -> None:
        client = self._make_client()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"ok": True, "result": {"file_id": "f1", "file_path": "photos/f1.jpg"}}
        mock_http = MagicMock()
        mock_http.post = AsyncMock(return_value=mock_resp)
        mock_http.is_closed = False
        client._http = mock_http

        result = await client.get_file("f1")
        assert result["file_path"] == "photos/f1.jpg"

    @pytest.mark.asyncio
    async def test_close(self) -> None:
        client = self._make_client()
        mock_http = MagicMock()
        mock_http.is_closed = False
        mock_http.aclose = AsyncMock()
        client._http = mock_http

        await client.close()
        mock_http.aclose.assert_called_once()
        assert client._http is None


# ── TelegramChannel Lifecycle Tests ──────────────────────────


class TestTelegramChannelLifecycle:
    @pytest.mark.asyncio
    async def test_start_success_webhook(self) -> None:
        ch = TelegramChannel(bot_token=FAKE_TELEGRAM_BOT_TOKEN, webhook_url="https://example.com/wh")
        ch._client = MagicMock()
        ch._client.get_me = AsyncMock(return_value={"id": 123, "username": "testbot"})
        ch._client.set_webhook = AsyncMock()

        with patch.object(ch, "_register_commands", new_callable=AsyncMock):
            with patch.object(ch, "_setup_webhook", new_callable=AsyncMock):
                await ch.start()

        assert ch._status == ChannelStatus.RUNNING

    @pytest.mark.asyncio
    async def test_start_no_token(self) -> None:
        ch = TelegramChannel(bot_token="")
        await ch.start()
        assert ch._status != ChannelStatus.RUNNING

    @pytest.mark.asyncio
    async def test_start_token_verification_fails(self) -> None:
        ch = _make_channel()
        ch._client = MagicMock()
        ch._client.get_me = AsyncMock(side_effect=TelegramApiError(401, "Unauthorized"))

        await ch.start()
        assert ch._status == ChannelStatus.ERROR

    @pytest.mark.asyncio
    async def test_stop(self) -> None:
        ch = _make_channel()
        ch._status = ChannelStatus.RUNNING
        ch._client = MagicMock()
        ch._client.close = AsyncMock()
        ch._client.delete_my_commands = AsyncMock()
        ch._client.delete_webhook = AsyncMock()
        ch._poll_task = None

        await ch.stop()
        assert ch._status == ChannelStatus.STOPPED
        ch._client.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_health_check_running(self) -> None:
        ch = _make_channel()
        ch._status = ChannelStatus.RUNNING
        ch._client = MagicMock()
        ch._client.verify_token = AsyncMock(return_value=True)

        assert await ch.health_check() is True

    @pytest.mark.asyncio
    async def test_health_check_stopped(self) -> None:
        ch = _make_channel()
        ch._status = ChannelStatus.STOPPED
        assert await ch.health_check() is False

    @pytest.mark.asyncio
    async def test_health_check_failure(self) -> None:
        ch = _make_channel()
        ch._status = ChannelStatus.RUNNING
        ch._client = MagicMock()
        ch._client.verify_token = AsyncMock(side_effect=Exception("network error"))

        assert await ch.health_check() is False

    def test_should_retry_429(self) -> None:
        ch = _make_channel()
        err = TelegramApiError(429, "Too Many Requests", {"retry_after": 10})
        assert ch.should_retry(err) is True

    def test_should_not_retry_401(self) -> None:
        ch = _make_channel()
        err = TelegramApiError(401, "Unauthorized")
        assert ch.should_retry(err) is False

    def test_extract_retry_after(self) -> None:
        ch = _make_channel()
        err = TelegramApiError(429, "Too Many Requests", {"retry_after": 30})
        assert ch.extract_retry_after(err) == 30.0

    def test_is_webhook_mode(self) -> None:
        ch = TelegramChannel(bot_token="tok", webhook_url="https://example.com/wh")
        assert ch.is_webhook_mode is True

    def test_is_polling_mode(self) -> None:
        ch = TelegramChannel(bot_token="tok")
        assert ch.is_webhook_mode is False

    def test_redact(self) -> None:
        ch = _make_channel()
        text = f"Error with token {ch._token}"
        redacted = ch._redact(text)
        assert ch._token not in redacted
        assert "REDACTED" in redacted

    def test_webhook_secret(self) -> None:
        ch = _make_channel()
        secret = ch.webhook_secret
        assert len(secret) == 32


# ── TelegramChannel Outbound Tests ───────────────────────────


class TestTelegramChannelOutbound:
    @pytest.mark.asyncio
    async def test_send_text(self) -> None:
        ch = _make_channel()
        ch._client = MagicMock()
        ch._client.send_message = AsyncMock(return_value={"message_id": 100})

        msg = OutboundMessage(channel="telegram", user_id="u1", recipient_id="42", content="Hello!")
        result = await ch.send(msg)
        assert result is not None
        ch._client.send_message.assert_called()

    @pytest.mark.asyncio
    async def test_send_empty_recipient(self) -> None:
        ch = _make_channel()
        msg = OutboundMessage(channel="telegram", user_id="u1", recipient_id="", content="Hello!")
        result = await ch.send(msg)
        assert result is None

    @pytest.mark.asyncio
    async def test_start_typing(self) -> None:
        ch = _make_channel()
        ch._client = MagicMock()
        ch._client.send_chat_action = AsyncMock()

        await ch.start_typing("42")
        ch._client.send_chat_action.assert_called_once_with("42", "typing")

    @pytest.mark.asyncio
    async def test_send_placeholder(self) -> None:
        ch = _make_channel()
        ch._draft_available = False
        ch._client = MagicMock()
        ch._client.send_message = AsyncMock(return_value={"message_id": 200})

        result = await ch.send_placeholder("42", "Thinking...")
        assert result == "200"

    @pytest.mark.asyncio
    async def test_edit_message(self) -> None:
        ch = _make_channel()
        ch._client = MagicMock()
        ch._client.edit_message_text = AsyncMock(return_value={"message_id": 100})

        await ch.edit_message("42", "100", "Updated text")
        ch._client.edit_message_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_edit_message_not_modified(self) -> None:
        ch = _make_channel()
        ch._client = MagicMock()
        ch._client.edit_message_text = AsyncMock(side_effect=TelegramApiError(400, "Bad Request: message is not modified"))

        await ch.edit_message("42", "100", "Same text")

    @pytest.mark.asyncio
    async def test_edit_message_parse_error_fallback(self) -> None:
        ch = _make_channel()
        ch._client = MagicMock()
        ch._client.edit_message_text = AsyncMock(
            side_effect=[
                TelegramApiError(400, "Bad Request: can't parse entities"),
                {"message_id": 100},
            ]
        )

        await ch.edit_message("42", "100", "**bold**")
        assert ch._client.edit_message_text.call_count == 2

    @pytest.mark.asyncio
    async def test_delete_message(self) -> None:
        ch = _make_channel()
        ch._client = MagicMock()
        ch._client.delete_message = AsyncMock(return_value=True)

        await ch.delete_message("42", "100")
        ch._client.delete_message.assert_called_once_with("42", 100)

    @pytest.mark.asyncio
    async def test_react_to_message(self) -> None:
        ch = _make_channel()
        ch._client = MagicMock()
        ch._client.set_message_reaction = AsyncMock()

        await ch.react_to_message("42", "100", "")
        ch._client.set_message_reaction.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_webhook_update(self) -> None:
        ch = _make_channel()
        received: list[object] = []

        async def handler(msg: object) -> None:
            received.append(msg)

        ch.set_inbound_handler(handler)
        ch._status = "running"

        update = {
            "update_id": 1,
            "message": {
                "message_id": 10,
                "from": {"id": 42},
                "chat": {"id": 42, "type": "private"},
                "text": "webhook hello",
            },
        }
        await ch.handle_webhook_update(update)
        assert len(received) == 1
        assert received[0].content == "webhook hello"

    @pytest.mark.asyncio
    async def test_edit_placeholder_message(self) -> None:
        ch = _make_channel()
        ch._client = MagicMock()
        ch._client.edit_message_text = AsyncMock(return_value={"message_id": 100})

        msg = OutboundMessage(channel="telegram", user_id="u1", recipient_id="42", content="Final answer")
        await ch.edit_placeholder_message("42", "100", msg)
        ch._client.edit_message_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_pin_message(self) -> None:
        ch = _make_channel()
        ch._client = MagicMock()
        ch._client.pin_chat_message = AsyncMock()

        await ch.pin_message("42", "100")
        ch._client.pin_chat_message.assert_called_once()

    def test_collect_issues_no_token(self) -> None:
        ch = TelegramChannel(bot_token="")
        issues = ch.collect_issues()
        assert any("token" in i.message.lower() for i in issues)

    def test_collect_issues_http_webhook(self) -> None:
        ch = TelegramChannel(bot_token="tok", webhook_url="http://insecure.com/wh")
        issues = ch.collect_issues()
        assert any("HTTPS" in i.message for i in issues)

    def test_collect_issues_healthy(self) -> None:
        ch = _make_channel()
        assert ch.collect_issues() == []

    def test_collect_issues_degraded(self) -> None:
        ch = _make_channel()
        ch._status = ChannelStatus.DEGRADED
        issues = ch.collect_issues()
        assert any("degraded" in i.message.lower() for i in issues)

    def test_collect_issues_health_error(self) -> None:
        ch = _make_channel()
        ch.health.record_failure("Connection timeout")
        issues = ch.collect_issues()
        assert any("timeout" in i.message.lower() for i in issues)


# ── Additional coverage tests ─────────────────────────────────


class TestTelegramStartPolling:
    @pytest.mark.asyncio
    async def test_start_polling_mode(self) -> None:
        ch = TelegramChannel(bot_token=FAKE_TELEGRAM_BOT_TOKEN)
        ch._client = MagicMock()
        ch._client.get_me = AsyncMock(return_value={"id": 123, "username": "testbot"})
        ch._client.delete_my_commands = AsyncMock()
        ch._client.delete_webhook = AsyncMock()

        with patch.object(ch, "_poll_loop", new_callable=AsyncMock):
            await ch.start()
            assert ch._status == ChannelStatus.RUNNING
            assert ch._poll_task is not None
            ch._poll_task.cancel()
            try:
                await ch._poll_task
            except asyncio.CancelledError:
                pass

    @pytest.mark.asyncio
    async def test_start_webhook_setup_fails_degrades(self) -> None:
        ch = TelegramChannel(bot_token=FAKE_TELEGRAM_BOT_TOKEN, webhook_url="https://example.com/wh")
        ch._client = MagicMock()
        ch._client.get_me = AsyncMock(return_value={"id": 123, "username": "testbot"})
        ch._client.delete_my_commands = AsyncMock()
        ch._client.set_webhook = AsyncMock(side_effect=TelegramApiError(400, "Bad Request"))

        await ch.start()
        assert ch._status == ChannelStatus.DEGRADED


class TestTelegramStopFull:
    @pytest.mark.asyncio
    async def test_stop_flushes_media_groups(self) -> None:
        ch = _make_channel()
        ch._status = ChannelStatus.RUNNING
        ch._client = MagicMock()
        ch._client.close = AsyncMock()
        ch._client.delete_my_commands = AsyncMock()
        ch._poll_task = None

        from app.channels.providers.telegram.channel import _MediaGroupBuffer
        from app.channels.types import InboundMessage

        buf = _MediaGroupBuffer()
        buf.messages.append(
            InboundMessage(
                channel="telegram",
                sender_id="42",
                chat_id="42",
                content="grouped",
                message_id="mg1",
            )
        )
        ch._mg_buffers["mg_key"] = buf

        emitted: list[object] = []

        async def _handler(msg: object) -> None:
            emitted.append(msg)

        ch.set_inbound_handler(_handler)

        await ch.stop()
        assert ch._status == ChannelStatus.STOPPED
        assert len(emitted) == 1

    @pytest.mark.asyncio
    async def test_stop_cancels_poll_task(self) -> None:
        ch = _make_channel()
        ch._status = ChannelStatus.RUNNING
        ch._client = MagicMock()
        ch._client.close = AsyncMock()
        ch._client.delete_my_commands = AsyncMock()

        async def _forever() -> None:
            await asyncio.sleep(999)

        ch._poll_task = asyncio.create_task(_forever())
        await ch.stop()
        assert ch._poll_task is None

    @pytest.mark.asyncio
    async def test_stop_webhook_mode_cleanup(self) -> None:
        ch = TelegramChannel(bot_token=FAKE_TELEGRAM_BOT_TOKEN, webhook_url="https://example.com/wh")
        ch._status = ChannelStatus.RUNNING
        ch._client = MagicMock()
        ch._client.close = AsyncMock()
        ch._client.delete_my_commands = AsyncMock()
        ch._client.delete_webhook = AsyncMock()
        ch._poll_task = None

        await ch.stop()
        ch._client.delete_webhook.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop_deletes_commands(self) -> None:
        from app.channels.providers.telegram.channel import BotCommand

        ch = _make_channel()
        ch._status = ChannelStatus.RUNNING
        ch._commands = [BotCommand(command="help", description="Help")]
        ch._client = MagicMock()
        ch._client.close = AsyncMock()
        ch._client.delete_my_commands = AsyncMock()
        ch._poll_task = None

        await ch.stop()
        ch._client.delete_my_commands.assert_called_once()


class TestTelegramHealthCheckVerifyFailed:
    @pytest.mark.asyncio
    async def test_health_check_verify_false(self) -> None:
        ch = _make_channel()
        ch._status = ChannelStatus.RUNNING
        ch._client = MagicMock()
        ch._client.verify_token = AsyncMock(return_value=False)

        assert await ch.health_check() is False


class TestTelegramSendMedia:
    @pytest.mark.asyncio
    async def test_send_with_media_attachment(self) -> None:
        ch = _make_channel()
        ch._client = MagicMock()
        ch._client.send_message = AsyncMock(return_value={"message_id": 100})

        with patch(
            "app.channels.providers.telegram.channel.send_media_attachment",
            new_callable=AsyncMock,
        ) as mock_send_media:
            msg = OutboundMessage(
                channel="telegram",
                user_id="u1",
                recipient_id="42",
                content="Check this out",
                media=(MediaAttachment(media_type=MediaType.IMAGE, url="https://img.example.com/photo.jpg"),),
            )
            result = await ch.send(msg)
            mock_send_media.assert_called_once()
            assert result == "100"

    @pytest.mark.asyncio
    async def test_send_html_parse_error_fallback(self) -> None:
        ch = _make_channel()
        ch._client = MagicMock()
        ch._client.send_message = AsyncMock(
            side_effect=[
                TelegramApiError(400, "Bad Request: can't parse entities"),
                {"message_id": 200},
            ]
        )

        msg = OutboundMessage(channel="telegram", user_id="u1", recipient_id="42", content="**bold**")
        result = await ch.send(msg)
        assert result == "200"
        assert ch._client.send_message.call_count == 2

    @pytest.mark.asyncio
    async def test_send_html_parse_error_raises_other(self) -> None:
        ch = _make_channel()
        ch._client = MagicMock()
        ch._client.send_message = AsyncMock(side_effect=TelegramApiError(400, "Bad Request: chat not found"))

        msg = OutboundMessage(channel="telegram", user_id="u1", recipient_id="42", content="hello")
        with pytest.raises(TelegramApiError, match="chat not found"):
            await ch.send(msg)


class TestTelegramSendPlaceholderParseError:
    @pytest.mark.asyncio
    async def test_placeholder_parse_error_fallback(self) -> None:
        ch = _make_channel()
        ch._draft_available = False
        ch._client = MagicMock()
        ch._client.send_message = AsyncMock(
            side_effect=[
                TelegramApiError(400, "Bad Request: can't parse entities"),
                {"message_id": 300},
            ]
        )

        result = await ch.send_placeholder("42", "**bold placeholder**")
        assert result == "300"
        assert ch._client.send_message.call_count == 2

    @pytest.mark.asyncio
    async def test_placeholder_other_error_returns_none(self) -> None:
        ch = _make_channel()
        ch._draft_available = False
        ch._client = MagicMock()
        ch._client.send_message = AsyncMock(side_effect=TelegramApiError(400, "Bad Request: chat not found"))

        result = await ch.send_placeholder("42", "text")
        assert result is None


class TestTelegramEditPlaceholderParseError:
    @pytest.mark.asyncio
    async def test_edit_placeholder_parse_error_fallback(self) -> None:
        ch = _make_channel()
        ch._client = MagicMock()
        ch._client.edit_message_text = AsyncMock(
            side_effect=[
                TelegramApiError(400, "Bad Request: can't parse entities"),
                {"message_id": 100},
            ]
        )

        msg = OutboundMessage(channel="telegram", user_id="u1", recipient_id="42", content="Final")
        await ch.edit_placeholder_message("42", "100", msg)
        assert ch._client.edit_message_text.call_count == 2

    @pytest.mark.asyncio
    async def test_edit_placeholder_not_modified(self) -> None:
        ch = _make_channel()
        ch._client = MagicMock()
        ch._client.edit_message_text = AsyncMock(side_effect=TelegramApiError(400, "Bad Request: message is not modified"))

        msg = OutboundMessage(channel="telegram", user_id="u1", recipient_id="42", content="Same")
        await ch.edit_placeholder_message("42", "100", msg)

    @pytest.mark.asyncio
    async def test_edit_placeholder_parse_error_inner_not_modified(self) -> None:
        ch = _make_channel()
        ch._client = MagicMock()
        ch._client.edit_message_text = AsyncMock(
            side_effect=[
                TelegramApiError(400, "Bad Request: can't parse entities"),
                TelegramApiError(400, "Bad Request: message is not modified"),
            ]
        )

        msg = OutboundMessage(channel="telegram", user_id="u1", recipient_id="42", content="Same")
        await ch.edit_placeholder_message("42", "100", msg)

    @pytest.mark.asyncio
    async def test_edit_placeholder_parse_error_inner_other(self) -> None:
        ch = _make_channel()
        ch._client = MagicMock()
        ch._client.edit_message_text = AsyncMock(
            side_effect=[
                TelegramApiError(400, "Bad Request: can't parse entities"),
                TelegramApiError(400, "Bad Request: message to edit not found"),
            ]
        )

        msg = OutboundMessage(channel="telegram", user_id="u1", recipient_id="42", content="text")
        await ch.edit_placeholder_message("42", "100", msg)

    @pytest.mark.asyncio
    async def test_edit_placeholder_other_error(self) -> None:
        ch = _make_channel()
        ch._client = MagicMock()
        ch._client.edit_message_text = AsyncMock(side_effect=TelegramApiError(400, "Bad Request: message to edit not found"))

        msg = OutboundMessage(channel="telegram", user_id="u1", recipient_id="42", content="text")
        await ch.edit_placeholder_message("42", "100", msg)


class TestTelegramEditMessageInner:
    @pytest.mark.asyncio
    async def test_edit_parse_error_inner_not_modified(self) -> None:
        ch = _make_channel()
        ch._client = MagicMock()
        ch._client.edit_message_text = AsyncMock(
            side_effect=[
                TelegramApiError(400, "Bad Request: can't parse entities"),
                TelegramApiError(400, "Bad Request: message is not modified"),
            ]
        )

        await ch.edit_message("42", "100", "text")

    @pytest.mark.asyncio
    async def test_edit_parse_error_inner_other_logs(self) -> None:
        ch = _make_channel()
        ch._client = MagicMock()
        ch._client.edit_message_text = AsyncMock(
            side_effect=[
                TelegramApiError(400, "Bad Request: can't parse entities"),
                TelegramApiError(400, "Bad Request: message to edit not found"),
            ]
        )

        await ch.edit_message("42", "100", "text")

    @pytest.mark.asyncio
    async def test_edit_other_error_logs(self) -> None:
        ch = _make_channel()
        ch._client = MagicMock()
        ch._client.edit_message_text = AsyncMock(side_effect=TelegramApiError(400, "Bad Request: message to edit not found"))

        await ch.edit_message("42", "100", "text")


class TestTelegramPinError:
    @pytest.mark.asyncio
    async def test_pin_message_error_silenced(self) -> None:
        ch = _make_channel()
        ch._client = MagicMock()
        ch._client.pin_chat_message = AsyncMock(side_effect=TelegramApiError(400, "Bad Request: not enough rights"))

        await ch.pin_message("42", "100")


class TestTelegramDownloadVoice:
    @pytest.mark.asyncio
    async def test_download_voice_message(self) -> None:
        from pathlib import Path

        ch = _make_channel()
        ch._client = MagicMock()
        ch._client.download_voice = AsyncMock(return_value=Path("/tmp/voice.ogg"))

        result = await ch.download_voice_message("file_123")
        assert result == Path("/tmp/voice.ogg")
        ch._client.download_voice.assert_called_once_with("file_123")


class TestTelegramRegisterCommands:
    @pytest.mark.asyncio
    async def test_register_commands_success(self) -> None:
        from app.channels.providers.telegram.channel import BotCommand

        ch = _make_channel()
        ch._commands = [BotCommand(command="help", description="Help")]
        ch._client = MagicMock()
        ch._client.set_my_commands = AsyncMock()

        await ch._register_commands()
        ch._client.set_my_commands.assert_called_once()

    @pytest.mark.asyncio
    async def test_register_commands_empty_deletes(self) -> None:
        ch = _make_channel()
        ch._commands = []
        ch._client = MagicMock()
        ch._client.delete_my_commands = AsyncMock()

        await ch._register_commands()
        ch._client.delete_my_commands.assert_called_once()

    @pytest.mark.asyncio
    async def test_register_commands_error_silenced(self) -> None:
        from app.channels.providers.telegram.channel import BotCommand

        ch = _make_channel()
        ch._commands = [BotCommand(command="help", description="Help")]
        ch._client = MagicMock()
        ch._client.set_my_commands = AsyncMock(side_effect=TelegramApiError(400, "Bad Request"))

        await ch._register_commands()


class TestTelegramWebhookSetup:
    @pytest.mark.asyncio
    async def test_setup_webhook(self) -> None:
        ch = TelegramChannel(bot_token=FAKE_TELEGRAM_BOT_TOKEN, webhook_url="https://example.com/wh")
        ch._client = MagicMock()
        ch._client.set_webhook = AsyncMock()

        await ch._setup_webhook()
        ch._client.set_webhook.assert_called_once()

    @pytest.mark.asyncio
    async def test_webhook_includes_message_reaction_in_allowed_updates(self) -> None:
        from app.channels.providers.telegram.inbound import _ALLOWED_UPDATES

        ch = TelegramChannel(bot_token=FAKE_TELEGRAM_BOT_TOKEN, webhook_url="https://example.com/wh")
        ch._client = MagicMock()
        ch._client.set_webhook = AsyncMock()

        await ch._setup_webhook()
        call_kwargs = ch._client.set_webhook.call_args
        assert call_kwargs.kwargs.get("allowed_updates") is _ALLOWED_UPDATES
        assert "message_reaction" in _ALLOWED_UPDATES

    @pytest.mark.asyncio
    async def test_cleanup_webhook(self) -> None:
        ch = _make_channel()
        ch._client = MagicMock()
        ch._client.delete_webhook = AsyncMock()

        await ch._cleanup_webhook()
        ch._client.delete_webhook.assert_called_once()

    @pytest.mark.asyncio
    async def test_cleanup_webhook_error_silenced(self) -> None:
        ch = _make_channel()
        ch._client = MagicMock()
        ch._client.delete_webhook = AsyncMock(side_effect=Exception("network"))

        await ch._cleanup_webhook()


class TestTelegramDraftStreaming:
    """Tests for sendMessageDraft streaming feature."""

    @pytest.mark.asyncio
    async def test_send_placeholder_draft_success(self) -> None:
        ch = _make_channel()
        ch._client = MagicMock()
        ch._client.send_message_draft = AsyncMock(return_value={"ok": True})

        result = await ch.send_placeholder("42", "Thinking...")
        assert result is not None
        assert result.startswith("draft:")
        assert ch._draft_available is True
        assert len(ch._active_drafts) == 1

    @pytest.mark.asyncio
    async def test_send_placeholder_draft_unavailable_falls_back(self) -> None:
        ch = _make_channel()
        ch._client = MagicMock()
        ch._client.send_message_draft = AsyncMock(side_effect=TelegramApiError(400, "Bad Request: unknown method"))
        ch._client.send_message = AsyncMock(return_value={"message_id": 200})

        result = await ch.send_placeholder("42", "Thinking...")
        assert result == "200"
        assert ch._draft_available is False

    @pytest.mark.asyncio
    async def test_send_placeholder_draft_cached_unavailable(self) -> None:
        ch = _make_channel()
        ch._draft_available = False
        ch._client = MagicMock()
        ch._client.send_message = AsyncMock(return_value={"message_id": 300})

        result = await ch.send_placeholder("42", "Thinking...")
        assert result == "300"
        ch._client.send_message_draft.assert_not_called()

    @pytest.mark.asyncio
    async def test_edit_message_draft_update(self) -> None:
        ch = _make_channel()
        ch._client = MagicMock()
        ch._client.send_message_draft = AsyncMock(return_value={"ok": True})

        placeholder_id = "draft:1"
        draft_key = ch._draft_key("42", placeholder_id)
        ch._active_drafts[draft_key] = 1

        await ch.edit_message("42", placeholder_id, "A" * 30)
        ch._client.send_message_draft.assert_called_once()

    @pytest.mark.asyncio
    async def test_edit_message_draft_min_chars_suppressed(self) -> None:
        ch = _make_channel()
        ch._client = MagicMock()
        ch._client.send_message_draft = AsyncMock()

        placeholder_id = "draft:1"
        draft_key = ch._draft_key("42", placeholder_id)
        ch._active_drafts[draft_key] = 1

        await ch.edit_message("42", placeholder_id, "Short")
        ch._client.send_message_draft.assert_not_called()

    @pytest.mark.asyncio
    async def test_edit_message_draft_id_protection(self) -> None:
        ch = _make_channel()
        ch._client = MagicMock()
        ch._client.edit_message_text = AsyncMock()

        await ch.edit_message("42", "draft:999", "A" * 30)
        ch._client.edit_message_text.assert_not_called()

    @pytest.mark.asyncio
    async def test_edit_placeholder_materializes_draft(self) -> None:
        ch = _make_channel()
        ch._client = MagicMock()
        ch._client.send_message_draft = AsyncMock(return_value={"ok": True})
        ch._client.send_message = AsyncMock(return_value={"message_id": 500})

        placeholder_id = "draft:1"
        draft_key = ch._draft_key("42", placeholder_id)
        ch._active_drafts[draft_key] = 1

        msg = OutboundMessage(channel="telegram", user_id="u1", recipient_id="42", content="Final answer")
        await ch.edit_placeholder_message("42", placeholder_id, msg)

        ch._client.send_message_draft.assert_called_once_with("42", 1, "", disable_notification=True)
        ch._client.send_message.assert_called_once()
        assert draft_key not in ch._active_drafts

    @pytest.mark.asyncio
    async def test_delete_message_clears_draft(self) -> None:
        ch = _make_channel()
        ch._client = MagicMock()
        ch._client.send_message_draft = AsyncMock(return_value={"ok": True})

        placeholder_id = "draft:1"
        draft_key = ch._draft_key("42", placeholder_id)
        ch._active_drafts[draft_key] = 1

        await ch.delete_message("42", placeholder_id)
        ch._client.send_message_draft.assert_called_once_with("42", 1, "", disable_notification=True)
        assert draft_key not in ch._active_drafts

    @pytest.mark.asyncio
    async def test_delete_regular_message_not_affected(self) -> None:
        ch = _make_channel()
        ch._client = MagicMock()
        ch._client.delete_message = AsyncMock(return_value=True)

        await ch.delete_message("42", "100")
        ch._client.delete_message.assert_called_once_with("42", 100)

    @pytest.mark.asyncio
    async def test_stop_clears_active_drafts(self) -> None:
        ch = _make_channel()
        ch._status = ChannelStatus.RUNNING
        ch._client = MagicMock()
        ch._client.close = AsyncMock()
        ch._client.delete_my_commands = AsyncMock()
        ch._client.send_message_draft = AsyncMock()
        ch._poll_task = None

        ch._active_drafts[ch._draft_key("42", "draft:1")] = 1
        ch._active_drafts[ch._draft_key("99", "draft:2")] = 2

        await ch.stop()
        assert len(ch._active_drafts) == 0
        assert ch._client.send_message_draft.call_count == 2

    @pytest.mark.asyncio
    async def test_stop_draft_cleanup_error_tolerated(self) -> None:
        ch = _make_channel()
        ch._status = ChannelStatus.RUNNING
        ch._client = MagicMock()
        ch._client.close = AsyncMock()
        ch._client.delete_my_commands = AsyncMock()
        ch._client.send_message_draft = AsyncMock(side_effect=Exception("network"))
        ch._poll_task = None

        ch._active_drafts[ch._draft_key("42", "draft:1")] = 1
        await ch.stop()
        assert len(ch._active_drafts) == 0
        assert ch._status == ChannelStatus.STOPPED

    def test_allocate_draft_id_wraps(self) -> None:
        ch = _make_channel()
        ch._draft_counter = 2_147_483_647
        new_id = ch._allocate_draft_id()
        assert new_id == 1

    def test_is_draft_id(self) -> None:
        ch = _make_channel()
        assert ch._is_draft_id("draft:123") is True
        assert ch._is_draft_id("100") is False

    @pytest.mark.asyncio
    async def test_try_send_draft_chat_restriction_not_global(self) -> None:
        ch = _make_channel()
        ch._client = MagicMock()
        ch._client.send_message_draft = AsyncMock(side_effect=TelegramApiError(400, "Bad Request: can't be used in groups"))

        result = await ch._try_send_draft("42", "text")
        assert result is None
        assert ch._draft_available is not False


class TestTelegramRetryMethods:
    def test_should_retry_non_telegram_error_delegates_to_base(self) -> None:
        ch = _make_channel()
        result = ch.should_retry(RuntimeError("generic"))
        assert isinstance(result, bool)

    def test_should_retry_403(self) -> None:
        ch = _make_channel()
        err = TelegramApiError(403, "Forbidden")
        assert ch.should_retry(err) is False

    def test_extract_retry_after_non_telegram_error(self) -> None:
        ch = _make_channel()
        assert ch.extract_retry_after(RuntimeError("generic")) is None

    def test_extract_retry_after_no_param(self) -> None:
        ch = _make_channel()
        err = TelegramApiError(429, "Too Many Requests")
        assert ch.extract_retry_after(err) is None


# ---------------------------------------------------------------------------
# Telegram helpers direct tests
# ---------------------------------------------------------------------------

from app.channels.providers.telegram.helpers import (  # noqa: E402
    build_inline_keyboard,
    send_media_attachment,
)
from app.channels.types.components import (  # noqa: E402
    ActionButton,
    SelectMenu,
    SelectOption,
)


class TestBuildInlineKeyboard:
    def test_no_elements(self) -> None:
        msg = OutboundMessage(
            channel="telegram",
            recipient_id="123",
            content="hi",
            user_id="U",
        )
        assert build_inline_keyboard(msg) is None

    def test_quick_replies(self) -> None:
        from app.channels.types import QuickReply

        msg = OutboundMessage(
            channel="telegram",
            recipient_id="123",
            content="hi",
            user_id="U",
            quick_replies=(QuickReply(label="Yes", text="yes"), QuickReply(label="No", text="no")),
        )
        result = build_inline_keyboard(msg)
        assert result is not None
        assert len(result["inline_keyboard"]) == 2

    def test_action_button_url(self) -> None:
        btn = ActionButton(action_id="a1", label="Visit", url="https://example.com")
        msg = OutboundMessage(
            channel="telegram",
            recipient_id="123",
            content="hi",
            user_id="U",
            components=((btn,),),
        )
        result = build_inline_keyboard(msg)
        assert result is not None
        rows = result["inline_keyboard"]
        assert rows[0][0]["url"] == "https://example.com"

    def test_action_button_callback(self) -> None:
        btn = ActionButton(action_id="a1", label="Click")
        msg = OutboundMessage(
            channel="telegram",
            recipient_id="123",
            content="hi",
            user_id="U",
            components=((btn,),),
        )
        result = build_inline_keyboard(msg)
        assert result is not None
        rows = result["inline_keyboard"]
        assert rows[0][0]["callback_data"].startswith("act:")

    def test_select_menu(self) -> None:
        menu = SelectMenu(
            action_id="s1",
            placeholder="Choose",
            options=(
                SelectOption(label="A", value="a"),
                SelectOption(label="B", value="b"),
            ),
        )
        msg = OutboundMessage(
            channel="telegram",
            recipient_id="123",
            content="hi",
            user_id="U",
            components=((menu,),),
        )
        result = build_inline_keyboard(msg)
        assert result is not None
        rows = result["inline_keyboard"]
        assert len(rows[0]) == 2


class TestSendMediaAttachment:
    @pytest.mark.asyncio
    async def test_send_image_url(self) -> None:
        client = MagicMock(spec=TelegramClient)
        client.send_photo = AsyncMock()
        att = MediaAttachment(media_type=MediaType.IMAGE, url="https://img.com/a.png")
        await send_media_attachment(client, "123", att, None)
        client.send_photo.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_document_fallback(self) -> None:
        client = MagicMock(spec=TelegramClient)
        client.send_document = AsyncMock()
        att = MediaAttachment(media_type=MediaType.DOCUMENT, url="https://example.com/file.pdf")
        await send_media_attachment(client, "123", att, "42")
        client.send_document.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_no_source_skipped(self) -> None:
        client = MagicMock(spec=TelegramClient)
        att = MediaAttachment(media_type=MediaType.IMAGE)
        await send_media_attachment(client, "123", att, None)

    @pytest.mark.asyncio
    async def test_send_with_filename(self) -> None:
        client = MagicMock(spec=TelegramClient)
        client.send_document = AsyncMock()
        att = MediaAttachment(
            media_type=MediaType.DOCUMENT,
            url="https://example.com/f.pdf",
            filename="report.pdf",
        )
        await send_media_attachment(client, "123", att, None)
        call_kwargs = client.send_document.call_args
        assert call_kwargs[1].get("filename") == "report.pdf"

    @pytest.mark.asyncio
    async def test_send_video(self) -> None:
        client = MagicMock(spec=TelegramClient)
        client.send_video = AsyncMock()
        att = MediaAttachment(media_type=MediaType.VIDEO, url="https://example.com/v.mp4")
        await send_media_attachment(client, "123", att, None)
        client.send_video.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_audio(self) -> None:
        client = MagicMock(spec=TelegramClient)
        client.send_voice = AsyncMock()
        att = MediaAttachment(media_type=MediaType.AUDIO, url="https://example.com/a.ogg")
        await send_media_attachment(client, "123", att, None)
        client.send_voice.assert_called_once()


# ══════════════════════════════════════════════════════════════════
# Forum Topic Management
# ══════════════════════════════════════════════════════════════════


def _make_topic_channel(*, auto_topic: bool = False) -> TelegramChannel:
    ch = TelegramChannel(
        bot_token=FAKE_TELEGRAM_BOT_TOKEN,
        auto_topic=auto_topic,
    )
    ch._bot_username = "testbot"
    ch._tg_bot_id = 123456789
    ch._client = MagicMock(spec=TelegramClient)
    return ch


class TestForumTopicChannel:
    """High-level Forum Topic methods on TelegramChannel."""

    @pytest.mark.asyncio
    async def test_create_topic_success(self) -> None:
        ch = _make_topic_channel()
        ch._client.create_forum_topic = AsyncMock(return_value={"message_thread_id": 99, "name": "Alice"})
        result = await ch.create_topic("-100123", "Alice")
        assert result == 99
        assert ch._topic_name_cache["-100123:99"] == "Alice"

    @pytest.mark.asyncio
    async def test_create_topic_failure(self) -> None:
        ch = _make_topic_channel()
        ch._client.create_forum_topic = AsyncMock(side_effect=TelegramApiError(403, "Forbidden: not enough rights"))
        result = await ch.create_topic("-100123", "Alice")
        assert result is None

    @pytest.mark.asyncio
    async def test_create_topic_no_thread_id(self) -> None:
        ch = _make_topic_channel()
        ch._client.create_forum_topic = AsyncMock(return_value={"name": "Alice"})
        result = await ch.create_topic("-100123", "Alice")
        assert result is None

    @pytest.mark.asyncio
    async def test_rename_topic_success(self) -> None:
        ch = _make_topic_channel()
        ch._client.edit_forum_topic = AsyncMock(return_value=True)
        assert await ch.rename_topic("-100123", 99, "Bob") is True
        assert ch._topic_name_cache["-100123:99"] == "Bob"

    @pytest.mark.asyncio
    async def test_rename_topic_failure(self) -> None:
        ch = _make_topic_channel()
        ch._client.edit_forum_topic = AsyncMock(side_effect=TelegramApiError(400, "Bad Request: topic not found"))
        assert await ch.rename_topic("-100123", 99, "Bob") is False

    @pytest.mark.asyncio
    async def test_close_topic_success(self) -> None:
        ch = _make_topic_channel()
        ch._client.close_forum_topic = AsyncMock(return_value=True)
        assert await ch.close_topic("-100123", 99) is True

    @pytest.mark.asyncio
    async def test_close_topic_failure(self) -> None:
        ch = _make_topic_channel()
        ch._client.close_forum_topic = AsyncMock(side_effect=TelegramApiError(400, "error"))
        assert await ch.close_topic("-100123", 99) is False

    @pytest.mark.asyncio
    async def test_reopen_topic_success(self) -> None:
        ch = _make_topic_channel()
        ch._client.reopen_forum_topic = AsyncMock(return_value=True)
        assert await ch.reopen_topic("-100123", 99) is True

    @pytest.mark.asyncio
    async def test_reopen_topic_failure(self) -> None:
        ch = _make_topic_channel()
        ch._client.reopen_forum_topic = AsyncMock(side_effect=TelegramApiError(400, "error"))
        assert await ch.reopen_topic("-100123", 99) is False


class TestAutoTopicCreation:
    """Test auto_topic mode: auto-create, sync name, and _pre_emit_hook."""

    @pytest.mark.asyncio
    async def test_ensure_topic_disabled(self) -> None:
        ch = _make_topic_channel(auto_topic=False)
        result = await ch.ensure_topic_for_user("-100123", "Alice", "42")
        assert result is None

    @pytest.mark.asyncio
    async def test_ensure_topic_creates(self) -> None:
        ch = _make_topic_channel(auto_topic=True)
        ch._client.create_forum_topic = AsyncMock(return_value={"message_thread_id": 55, "name": "Alice"})
        result = await ch.ensure_topic_for_user("-100123", "Alice", "42")
        assert result == 55
        assert ch._user_topic_map["-100123:42"] == 55

    @pytest.mark.asyncio
    async def test_ensure_topic_reuses_existing(self) -> None:
        """Second call for same user should reuse cached topic, not create new one."""
        ch = _make_topic_channel(auto_topic=True)
        ch._client.create_forum_topic = AsyncMock(return_value={"message_thread_id": 55, "name": "Alice"})
        first = await ch.ensure_topic_for_user("-100123", "Alice", "42")
        second = await ch.ensure_topic_for_user("-100123", "Alice", "42")
        assert first == second == 55
        assert ch._client.create_forum_topic.call_count == 1

    @pytest.mark.asyncio
    async def test_ensure_topic_concurrent_lock(self) -> None:
        """Concurrent calls for the same user should serialize and only create once."""
        ch = _make_topic_channel(auto_topic=True)

        async def mock_create(*_a: object, **_kw: object) -> dict[str, object]:
            await asyncio.sleep(0.01)
            return {"message_thread_id": 61, "name": "Alice"}

        ch._client.create_forum_topic = AsyncMock(side_effect=mock_create)
        results = await asyncio.gather(
            ch.ensure_topic_for_user("-100123", "Alice", "42"),
            ch.ensure_topic_for_user("-100123", "Alice", "42"),
        )
        assert all(r == 61 for r in results)
        assert ch._client.create_forum_topic.call_count == 1

    @pytest.mark.asyncio
    async def test_sync_topic_name_no_change(self) -> None:
        ch = _make_topic_channel(auto_topic=True)
        ch._topic_name_cache["-100123:99"] = "Alice"
        ch._client.edit_forum_topic = AsyncMock(return_value=True)
        await ch.sync_topic_name("-100123", 99, "Alice")
        ch._client.edit_forum_topic.assert_not_called()

    @pytest.mark.asyncio
    async def test_sync_topic_name_changed(self) -> None:
        ch = _make_topic_channel(auto_topic=True)
        ch._topic_name_cache["-100123:99"] = "Alice"
        ch._client.edit_forum_topic = AsyncMock(return_value=True)
        await ch.sync_topic_name("-100123", 99, "Alice Smith")
        ch._client.edit_forum_topic.assert_called_once_with("-100123", 99, name="Alice Smith")

    @pytest.mark.asyncio
    async def test_sync_topic_name_disabled(self) -> None:
        ch = _make_topic_channel(auto_topic=False)
        ch._client.edit_forum_topic = AsyncMock()
        await ch.sync_topic_name("-100123", 99, "Alice")
        ch._client.edit_forum_topic.assert_not_called()

    @pytest.mark.asyncio
    async def test_pre_emit_hook_forum_no_thread(self) -> None:
        """Forum message without thread_id should trigger auto-create."""
        from app.channels.types import InboundMessage

        ch = _make_topic_channel(auto_topic=True)
        ch._client.create_forum_topic = AsyncMock(return_value={"message_thread_id": 77, "name": "Bob"})
        msg = InboundMessage(
            channel="telegram",
            sender_id="42",
            content="hello",
            chat_id="-100123",
            sender_name="Bob",
            is_group=True,
            thread_id=None,
            metadata={"is_forum": True},
        )
        result = await ch._pre_emit_hook(msg)
        assert result.thread_id == "77"
        ch._client.create_forum_topic.assert_called_once()

    @pytest.mark.asyncio
    async def test_pre_emit_hook_forum_with_thread(self) -> None:
        """Forum message with existing thread_id should populate user_topic_map and trigger name sync."""
        from app.channels.types import InboundMessage

        ch = _make_topic_channel(auto_topic=True)
        ch._topic_name_cache["-100123:99"] = "Old Name"
        ch._client.edit_forum_topic = AsyncMock(return_value=True)
        msg = InboundMessage(
            channel="telegram",
            sender_id="42",
            content="hello",
            chat_id="-100123",
            sender_name="New Name",
            is_group=True,
            thread_id="99",
            metadata={"is_forum": True},
        )
        result = await ch._pre_emit_hook(msg)
        assert result is msg
        assert ch._user_topic_map["-100123:42"] == 99
        await asyncio.sleep(0.05)
        ch._client.edit_forum_topic.assert_called_once_with("-100123", 99, name="New Name")

    @pytest.mark.asyncio
    async def test_pre_emit_hook_non_forum(self) -> None:
        """Non-forum messages pass through unchanged."""
        from app.channels.types import InboundMessage

        ch = _make_topic_channel(auto_topic=True)
        msg = InboundMessage(
            channel="telegram",
            sender_id="42",
            content="hello",
            chat_id="-100123",
            is_group=True,
            metadata={"is_forum": False},
        )
        result = await ch._pre_emit_hook(msg)
        assert result is msg

    @pytest.mark.asyncio
    async def test_pre_emit_hook_disabled(self) -> None:
        """Auto-topic disabled passes through unchanged."""
        from app.channels.types import InboundMessage

        ch = _make_topic_channel(auto_topic=False)
        msg = InboundMessage(
            channel="telegram",
            sender_id="42",
            content="hello",
            chat_id="-100123",
            is_group=True,
            metadata={"is_forum": True},
        )
        result = await ch._pre_emit_hook(msg)
        assert result is msg


class TestFromCredentialsAutoTopic:
    """Test that from_credentials correctly parses auto_topic credential."""

    def test_auto_topic_false_by_default(self) -> None:
        ch = TelegramChannel.from_credentials({"token": "test:tok"})
        assert ch._auto_topic is False

    def test_auto_topic_true(self) -> None:
        ch = TelegramChannel.from_credentials({"token": "test:tok", "auto_topic": "true"})
        assert ch._auto_topic is True

    def test_auto_topic_yes(self) -> None:
        ch = TelegramChannel.from_credentials({"token": "test:tok", "auto_topic": "yes"})
        assert ch._auto_topic is True

    def test_auto_topic_1(self) -> None:
        ch = TelegramChannel.from_credentials({"token": "test:tok", "auto_topic": "1"})
        assert ch._auto_topic is True


class TestAutoTopicEdgeCases:
    """Edge cases for auto-topic: failures, empty fields, DM, system messages."""

    @pytest.mark.asyncio
    async def test_ensure_topic_create_fails(self) -> None:
        """ensure_topic_for_user returns None when create_topic fails."""
        ch = _make_topic_channel(auto_topic=True)
        ch._client.create_forum_topic = AsyncMock(side_effect=TelegramApiError(403, "Bot is not admin"))
        result = await ch.ensure_topic_for_user("-100123", "Alice", "42")
        assert result is None
        assert "-100123:42" not in ch._user_topic_map

    @pytest.mark.asyncio
    async def test_apply_auto_topic_dm_message(self) -> None:
        """DM (non-group) messages pass through even if auto_topic is on."""
        from app.channels.types import InboundMessage

        ch = _make_topic_channel(auto_topic=True)
        msg = InboundMessage(
            channel="telegram",
            sender_id="42",
            content="hi",
            chat_id="42",
            is_group=False,
            metadata={"is_forum": False},
        )
        result = await ch._pre_emit_hook(msg)
        assert result is msg

    @pytest.mark.asyncio
    async def test_apply_auto_topic_no_sender_id(self) -> None:
        """Forum message without sender_id passes through unchanged."""
        from app.channels.types import InboundMessage

        ch = _make_topic_channel(auto_topic=True)
        msg = InboundMessage(
            channel="telegram",
            sender_id="",
            content="system event",
            chat_id="-100123",
            is_group=True,
            thread_id=None,
            metadata={"is_forum": True},
        )
        result = await ch._pre_emit_hook(msg)
        assert result is msg

    @pytest.mark.asyncio
    async def test_sync_topic_name_rename_fails(self) -> None:
        """sync_topic_name handles rename failure gracefully."""
        ch = _make_topic_channel(auto_topic=True)
        ch._topic_name_cache["-100123:99"] = "Old"
        ch._client.edit_forum_topic = AsyncMock(side_effect=TelegramApiError(400, "Topic not found"))
        await ch.sync_topic_name("-100123", 99, "New Name")
        assert ch._topic_name_cache["-100123:99"] == "Old"

    @pytest.mark.asyncio
    async def test_sync_topic_name_no_cache(self) -> None:
        """sync_topic_name calls rename when no cache entry exists."""
        ch = _make_topic_channel(auto_topic=True)
        ch._client.edit_forum_topic = AsyncMock(return_value=True)
        await ch.sync_topic_name("-100123", 99, "Alice")
        ch._client.edit_forum_topic.assert_called_once_with("-100123", 99, name="Alice")
        assert ch._topic_name_cache["-100123:99"] == "Alice"

    @pytest.mark.asyncio
    async def test_create_topic_with_icon(self) -> None:
        """create_topic passes icon parameters to API."""
        ch = _make_topic_channel(auto_topic=True)
        ch._client.create_forum_topic = AsyncMock(return_value={"message_thread_id": 88, "name": "Test"})
        result = await ch.create_topic("-100123", "Test", icon_color=0x6FB9F0, icon_custom_emoji_id="5368324170671202286")
        assert result == 88
        ch._client.create_forum_topic.assert_called_once_with(
            "-100123",
            "Test",
            icon_color=0x6FB9F0,
            icon_custom_emoji_id="5368324170671202286",
        )

    @pytest.mark.asyncio
    async def test_ensure_topic_empty_sender_name(self) -> None:
        """Fallback to 'User {id}' when sender_name is empty."""
        ch = _make_topic_channel(auto_topic=True)
        ch._client.create_forum_topic = AsyncMock(return_value={"message_thread_id": 66, "name": "User 42"})
        result = await ch.ensure_topic_for_user("-100123", "", "42")
        assert result == 66
        ch._client.create_forum_topic.assert_called_once_with(
            "-100123",
            "User 42",
            icon_color=None,
            icon_custom_emoji_id=None,
        )

    @pytest.mark.asyncio
    async def test_pre_emit_hook_preserves_all_fields(self) -> None:
        """When auto-create triggers, all original message fields are preserved."""
        from app.channels.types import InboundMessage

        ch = _make_topic_channel(auto_topic=True)
        ch._client.create_forum_topic = AsyncMock(return_value={"message_thread_id": 99, "name": "Alice"})
        msg = InboundMessage(
            channel="telegram",
            sender_id="42",
            content="test content",
            chat_id="-100123",
            sender_name="Alice",
            is_group=True,
            is_bot=False,
            mentioned=True,
            reply_to_id="5",
            thread_id=None,
            metadata={"is_forum": True, "chat_type": "supergroup"},
            message_id="12345",
        )
        result = await ch._pre_emit_hook(msg)
        assert result.thread_id == "99"
        assert result.sender_id == "42"
        assert result.content == "test content"
        assert result.chat_id == "-100123"
        assert result.sender_name == "Alice"
        assert result.is_group is True
        assert result.is_bot is False
        assert result.mentioned is True
        assert result.reply_to_id == "5"
        assert result.metadata == {"is_forum": True, "chat_type": "supergroup"}
        assert result.message_id == "12345"
        assert result.channel == "telegram"

    @pytest.mark.asyncio
    async def test_user_topic_map_different_chats(self) -> None:
        """Different chat_ids create separate topics for the same user."""
        ch = _make_topic_channel(auto_topic=True)
        call_count = 0

        async def mock_create(chat_id: str, name: str, **_kw: object) -> dict[str, object]:
            nonlocal call_count
            call_count += 1
            return {"message_thread_id": 100 + call_count, "name": name}

        ch._client.create_forum_topic = AsyncMock(side_effect=mock_create)
        r1 = await ch.ensure_topic_for_user("-100A", "Alice", "42")
        r2 = await ch.ensure_topic_for_user("-100B", "Alice", "42")
        assert r1 != r2
        assert ch._client.create_forum_topic.call_count == 2


# ══════════════════════════════════════════════════════════════════
# Polling Conflict Smart Recovery
# ══════════════════════════════════════════════════════════════════


class TestIsPollingConflict:
    """Unit tests for _is_polling_conflict static method."""

    def test_409_conflict_text(self) -> None:
        err = Exception("Telegram API 409: Conflict: terminated by other getUpdates request")
        assert TelegramChannel._is_polling_conflict(err) is True

    def test_terminated_by_other_request(self) -> None:
        err = Exception("terminated by other getUpdates request")
        assert TelegramChannel._is_polling_conflict(err) is True

    def test_conflict_in_type_name(self) -> None:
        class ConflictError(Exception):
            pass

        err = ConflictError("polling failed")
        assert TelegramChannel._is_polling_conflict(err) is True

    def test_409_and_conflict_keywords(self) -> None:
        err = Exception("Error 409: conflict detected")
        assert TelegramChannel._is_polling_conflict(err) is True

    def test_409_without_conflict_keyword(self) -> None:
        err = Exception("Error 409: something else")
        assert TelegramChannel._is_polling_conflict(err) is False

    def test_network_error_not_conflict(self) -> None:
        err = Exception("Connection timeout")
        assert TelegramChannel._is_polling_conflict(err) is False

    def test_generic_api_error_not_conflict(self) -> None:
        err = TelegramApiError(500, "Internal Server Error")
        assert TelegramChannel._is_polling_conflict(err) is False

    def test_telegram_api_409_conflict(self) -> None:
        err = TelegramApiError(409, "Conflict: terminated by other getUpdates request")
        assert TelegramChannel._is_polling_conflict(err) is True


import app.channels.providers.telegram.inbound as _tg_inbound_mod  # noqa: E402


class TestPollLoopConflictRecovery:
    """Integration tests for _poll_loop conflict error handling."""

    @pytest.mark.asyncio
    async def test_conflict_retries_then_stops(self) -> None:
        """After _MAX_CONFLICT_RETRIES conflicts, loop stops with ERROR status."""
        from app.channels.providers.telegram.helpers import (
            _MAX_CONFLICT_RETRIES,
        )

        ch = _make_channel()
        ch._status = ChannelStatus.RUNNING
        ch._offset = 0
        ch._client = MagicMock()
        ch._client.get_updates = AsyncMock(side_effect=TelegramApiError(409, "Conflict: terminated by other getUpdates request"))

        with patch.object(_tg_inbound_mod.asyncio, "sleep", new_callable=AsyncMock):
            await ch._poll_loop()

        assert ch._status == ChannelStatus.ERROR
        assert ch._client.get_updates.call_count == _MAX_CONFLICT_RETRIES + 1
        assert ch.health.last_error is not None
        assert "polling" in ch.health.last_error.lower()

    @pytest.mark.asyncio
    async def test_conflict_resolves_before_max_retries(self) -> None:
        """Conflict errors that resolve within limit allow recovery."""
        ch = _make_channel()
        ch._status = ChannelStatus.RUNNING
        ch._offset = 0
        ch._client = MagicMock()

        call_count = 0

        async def get_updates_side_effect(**kwargs: object) -> list[dict[str, object]]:
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                raise TelegramApiError(409, "Conflict: terminated by other getUpdates request")
            if call_count == 3:
                return [
                    {
                        "update_id": 1,
                        "message": {"message_id": 1, "from": {"id": 42}, "chat": {"id": 42, "type": "private"}, "text": "hello"},
                    }
                ]
            ch._status = ChannelStatus.STOPPED
            return []

        ch._client.get_updates = AsyncMock(side_effect=get_updates_side_effect)
        ch.set_inbound_handler(AsyncMock())

        with patch.object(_tg_inbound_mod.asyncio, "sleep", new_callable=AsyncMock):
            await ch._poll_loop()

        assert ch._status == ChannelStatus.STOPPED
        assert ch.health.last_error is None or "conflict" not in (ch.health.last_error or "").lower()


class TestPollLoopNetworkRecovery:
    """Integration tests for _poll_loop network error handling."""

    @pytest.mark.asyncio
    async def test_network_errors_degrade_then_recover(self) -> None:
        """Network errors trigger DEGRADED; successful poll restores RUNNING."""
        from app.channels.providers.telegram.helpers import (
            _DEGRADED_THRESHOLD,
        )

        ch = _make_channel()
        ch._status = ChannelStatus.RUNNING
        ch._offset = 0
        ch._client = MagicMock()

        call_count = 0

        async def get_updates_side_effect(**kwargs: object) -> list[dict[str, object]]:
            nonlocal call_count
            call_count += 1
            if call_count <= _DEGRADED_THRESHOLD:
                raise OSError("Connection reset by peer")
            if call_count == _DEGRADED_THRESHOLD + 1:
                return []
            ch._status = ChannelStatus.STOPPED
            return []

        ch._client.get_updates = AsyncMock(side_effect=get_updates_side_effect)

        with patch.object(_tg_inbound_mod.asyncio, "sleep", new_callable=AsyncMock):
            await ch._poll_loop()

        assert ch._status == ChannelStatus.STOPPED
        assert ch.is_connected is True

    @pytest.mark.asyncio
    async def test_network_errors_below_threshold_stay_running(self) -> None:
        """Network errors below _DEGRADED_THRESHOLD keep RUNNING status."""
        ch = _make_channel()
        ch._status = ChannelStatus.RUNNING
        ch._offset = 0
        ch._client = MagicMock()

        call_count = 0

        async def get_updates_side_effect(**kwargs: object) -> list[dict[str, object]]:
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                raise OSError("Network unreachable")
            ch._status = ChannelStatus.STOPPED
            return []

        ch._client.get_updates = AsyncMock(side_effect=get_updates_side_effect)

        with patch.object(_tg_inbound_mod.asyncio, "sleep", new_callable=AsyncMock):
            await ch._poll_loop()

        assert ch._status == ChannelStatus.STOPPED

    @pytest.mark.asyncio
    async def test_degraded_status_continues_polling(self) -> None:
        """Polling continues when status is DEGRADED (not stuck)."""
        from app.channels.providers.telegram.helpers import (
            _DEGRADED_THRESHOLD,
        )

        ch = _make_channel()
        ch._status = ChannelStatus.RUNNING
        ch._offset = 0
        ch._client = MagicMock()

        call_count = 0

        async def get_updates_side_effect(**kwargs: object) -> list[dict[str, object]]:
            nonlocal call_count
            call_count += 1
            if call_count <= _DEGRADED_THRESHOLD + 2:
                raise OSError("Connection timeout")
            # After recovery, stop the loop
            ch._status = ChannelStatus.STOPPED
            return []

        ch._client.get_updates = AsyncMock(side_effect=get_updates_side_effect)

        with patch.object(_tg_inbound_mod.asyncio, "sleep", new_callable=AsyncMock):
            await ch._poll_loop()

        # Must have polled beyond threshold (proves DEGRADED didn't exit loop)
        assert call_count > _DEGRADED_THRESHOLD

    @pytest.mark.asyncio
    async def test_cancelled_error_breaks_loop(self) -> None:
        """CancelledError cleanly exits the loop."""
        ch = _make_channel()
        ch._status = ChannelStatus.RUNNING
        ch._offset = 0
        ch._client = MagicMock()
        ch._client.get_updates = AsyncMock(side_effect=asyncio.CancelledError)

        await ch._poll_loop()
        assert ch._status == ChannelStatus.RUNNING

    @pytest.mark.asyncio
    async def test_successful_poll_resets_backoff(self) -> None:
        """After recovery from errors, conflict_count and consecutive_errors reset."""
        ch = _make_channel()
        ch._status = ChannelStatus.RUNNING
        ch._offset = 0
        ch._client = MagicMock()

        call_count = 0

        async def get_updates_side_effect(**kwargs: object) -> list[dict[str, object]]:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise OSError("Transient error")
            if call_count == 2:
                return []
            if call_count == 3:
                raise OSError("Another transient")
            if call_count == 4:
                return []
            ch._status = ChannelStatus.STOPPED
            return []

        ch._client.get_updates = AsyncMock(side_effect=get_updates_side_effect)

        with patch.object(_tg_inbound_mod.asyncio, "sleep", new_callable=AsyncMock):
            await ch._poll_loop()

        assert ch._status == ChannelStatus.STOPPED

    @pytest.mark.asyncio
    async def test_poll_loop_processes_updates_normally(self) -> None:
        """Normal poll loop processes updates and advances offset."""
        ch = _make_channel()
        ch._status = ChannelStatus.RUNNING
        ch._offset = 0
        ch._client = MagicMock()
        received: list[object] = []

        async def handler(msg: object) -> None:
            received.append(msg)

        ch.set_inbound_handler(handler)

        call_count = 0

        async def get_updates_side_effect(**kwargs: object) -> list[dict[str, object]]:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return [
                    {
                        "update_id": 100,
                        "message": {
                            "message_id": 1,
                            "from": {"id": 42, "username": "alice"},
                            "chat": {"id": 42, "type": "private"},
                            "text": "hello",
                        },
                    }
                ]
            ch._status = ChannelStatus.STOPPED
            return []

        ch._client.get_updates = AsyncMock(side_effect=get_updates_side_effect)

        await ch._poll_loop()
        assert ch._offset == 101
        assert len(received) == 1


# ------------------------------------------------------------------
# Table degradation in md_to_telegram_html
# ------------------------------------------------------------------
from app.channels.providers.telegram.html_converter import (  # noqa: E402
    md_to_telegram_html,
    split_message,
)


class TestTableDegradation:
    """Verify GFM tables degrade to <pre> monospace ASCII tables in HTML path."""

    def test_basic_table_converted(self) -> None:
        md = "| A | B |\n|---|---|\n| 1 | 2 |"
        result = md_to_telegram_html(md)
        assert "<pre>" in result
        assert "┌" in result and "┘" in result
        assert "1" in result and "2" in result

    def test_table_with_surrounding_text(self) -> None:
        md = "Hello\n\n| X | Y |\n|---|---|\n| a | b |\n\nBye"
        result = md_to_telegram_html(md)
        assert "Hello" in result
        assert "Bye" in result
        assert "┌" in result

    def test_code_block_table_not_converted(self) -> None:
        md = "```\n| A | B |\n|---|---|\n| 1 | 2 |\n```"
        result = md_to_telegram_html(md)
        assert "┌" not in result

    def test_no_data_rows_not_converted(self) -> None:
        md = "| A | B |\n|---|---|"
        result = md_to_telegram_html(md)
        assert "┌" not in result

    def test_multiple_tables(self) -> None:
        md = "| A | B |\n|---|---|\n| 1 | 2 |\n\n| X | Y |\n|---|---|\n| 3 | 4 |"
        result = md_to_telegram_html(md)
        assert result.count("┌") == 2

    def test_html_entities_escaped_in_table(self) -> None:
        md = "| Key | Value |\n|-----|-------|\n| a<b | 1&2 |"
        result = md_to_telegram_html(md)
        assert "&lt;" in result or "&amp;" in result

    def test_alignment_markers(self) -> None:
        md = "| L | C | R |\n|:--|:-:|--:|\n| a | b | c |"
        result = md_to_telegram_html(md)
        assert "┌" in result

    def test_uneven_columns_padded(self) -> None:
        md = "| A | B | C |\n|---|---|---|\n| 1 | 2 |"
        result = md_to_telegram_html(md)
        assert "┌" in result

    def test_no_table_unchanged(self) -> None:
        md = "Hello **world**"
        result = md_to_telegram_html(md)
        assert "┌" not in result
        assert "<b>world</b>" in result

    def test_table_split_message_compatibility(self) -> None:
        md = "| A | B |\n|---|---|\n| 1 | 2 |"
        html_result = md_to_telegram_html(md)
        chunks = split_message(html_result)
        assert len(chunks) >= 1
        assert "┌" in chunks[0]
