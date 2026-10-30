"""Inbound parsing: callback_query, location, venue and message_reaction updates."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from tests.channels.providers.telegram.telegram_channel_factories import make_channel


class TestParseUpdateCallbackQuery:
    """callback_query updates become prefixed commands."""

    @pytest.mark.asyncio
    async def test_callback_query(self) -> None:
        ch = make_channel()
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
        ch = make_channel()
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
        ch = make_channel()
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


class TestParseUpdateLocation:
    """Location and venue messages become a map link."""

    def test_location_message(self) -> None:
        ch = make_channel()
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
        ch = make_channel()
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
        ch = make_channel()
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
        ch = make_channel()
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
        ch = make_channel()
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
        ch = make_channel()
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
        ch = make_channel()
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


class TestParseUpdateReaction:
    """message_reaction updates become the emoji picked."""

    def test_message_reaction_emoji(self) -> None:
        ch = make_channel()
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
        ch = make_channel()
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
        ch = make_channel()
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
        ch = make_channel()
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
        ch = make_channel()
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
        ch = make_channel()
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
