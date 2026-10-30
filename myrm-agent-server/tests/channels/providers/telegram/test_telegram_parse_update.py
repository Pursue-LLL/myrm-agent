"""Inbound parsing: Pydantic update models, messages, callback queries and media-group buffering."""

from __future__ import annotations

import pytest

from app.channels.providers.telegram.models import (
    TgMessage,
    TgUpdate,
)
from app.channels.types import (
    ChannelStatus,
    InboundMessage,
    MediaType,
)
from tests.channels.providers.telegram.telegram_channel_factories import make_channel


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
        ch = make_channel()
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
        ch = make_channel()
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
        ch = make_channel()
        assert ch._parse_update({"update_id": 3}) is None

    def test_no_from_returns_none(self) -> None:
        ch = make_channel()
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
        ch = make_channel()
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
        ch = make_channel()
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
        ch = make_channel()
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
        ch = make_channel()
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
        ch = make_channel()
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
        ch = make_channel()
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

    def test_thread_id_parsed(self) -> None:
        ch = make_channel()
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

    def test_invalid_payload_returns_none(self) -> None:
        """Completely invalid payload should be handled gracefully."""
        ch = make_channel()
        assert ch._parse_update({}) is None

    def test_audio_message(self) -> None:
        ch = make_channel()
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


class TestBufferOrEmit:
    @pytest.mark.asyncio
    async def test_non_media_group_emits_directly(self) -> None:
        ch = make_channel()
        received: list[InboundMessage] = []

        async def handler(msg: InboundMessage) -> None:
            received.append(msg)

        ch.set_inbound_handler(handler)
        ch._status = ChannelStatus.RUNNING

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
        ch = make_channel()
        received: list[InboundMessage] = []

        async def handler(msg: InboundMessage) -> None:
            received.append(msg)

        ch.set_inbound_handler(handler)
        ch._status = ChannelStatus.RUNNING

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
