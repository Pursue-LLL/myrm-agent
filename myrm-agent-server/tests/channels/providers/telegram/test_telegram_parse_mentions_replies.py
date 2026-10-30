"""Inbound parsing: group mention detection and replied-to message context."""

from __future__ import annotations

from app.channels.types import (
    METADATA_EXPLICIT_MENTION_KEY,
    MediaType,
)
from tests.channels.providers.telegram.telegram_channel_factories import make_channel


class TestParseUpdateMentions:
    """Group mention detection by entity, caption and reply."""

    def test_group_message_with_mention(self) -> None:
        ch = make_channel()
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
        ch = make_channel()
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
        ch = make_channel()
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
        ch = make_channel()
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
        ch = make_channel()
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
        ch = make_channel()
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


class TestParseUpdateReplyContext:
    """The replied-to message becomes a ReplyContext."""

    def test_reply_to_caption_message(self) -> None:
        ch = make_channel()
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
        ch = make_channel()
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
        ch = make_channel()
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
        ch = make_channel()
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
        ch = make_channel()
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
        ch = make_channel()
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
