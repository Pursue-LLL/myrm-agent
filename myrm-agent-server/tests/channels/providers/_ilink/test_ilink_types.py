"""Tests for ilink_types.parse_item — including type/sub-key fallback."""

from __future__ import annotations

from app.channels.providers._ilink.types import (
    ItemType,
    parse_item,
)

# ── Normal parsing (type matches sub-key) ─────────────────────────────


class TestParseItemNormal:
    def test_text(self) -> None:
        result = parse_item({"type": ItemType.TEXT, "text_item": {"text": "hello"}})
        assert result is not None
        assert result.type == ItemType.TEXT
        assert result.text_item is not None
        assert result.text_item.text == "hello"

    def test_image_with_url(self) -> None:
        result = parse_item({"type": ItemType.IMAGE, "image_item": {"url": "https://img.example.com/a.jpg"}})
        assert result is not None
        assert result.type == ItemType.IMAGE
        assert result.image_item is not None
        assert result.image_item.url == "https://img.example.com/a.jpg"

    def test_image_with_media(self) -> None:
        result = parse_item(
            {
                "type": ItemType.IMAGE,
                "image_item": {
                    "media": {"encrypt_query_param": "foo=bar", "aes_key": "abc123"},
                },
            }
        )
        assert result is not None
        assert result.image_item is not None
        assert result.image_item.media is not None

    def test_voice_with_media(self) -> None:
        result = parse_item(
            {
                "type": ItemType.VOICE,
                "voice_item": {
                    "media": {"encrypt_query_param": "p=1", "aes_key": "k"},
                    "playtime": 5,
                },
            }
        )
        assert result is not None
        assert result.voice_item is not None
        assert result.voice_item.playtime == 5

    def test_file_with_media(self) -> None:
        result = parse_item(
            {
                "type": ItemType.FILE,
                "file_item": {
                    "media": {"encrypt_query_param": "p=1", "aes_key": "k"},
                    "file_name": "doc.pdf",
                },
            }
        )
        assert result is not None
        assert result.file_item is not None
        assert result.file_item.file_name == "doc.pdf"

    def test_video_with_media(self) -> None:
        result = parse_item(
            {
                "type": ItemType.VIDEO,
                "video_item": {
                    "media": {"encrypt_query_param": "p=1", "aes_key": "k"},
                },
            }
        )
        assert result is not None
        assert result.video_item is not None
        assert result.video_item.media is not None

    def test_unknown_type_returns_none(self) -> None:
        assert parse_item({"type": 99}) is None

    def test_empty_text_returns_none(self) -> None:
        assert parse_item({"type": ItemType.TEXT, "text_item": {"text": ""}}) is None


# ── Fallback: type/sub-key mismatch ───────────────────────────────────


class TestParseItemFallback:
    """Regression: iLink API sometimes sends type=VIDEO but payload has file_item."""

    def test_type_video_but_file_item_present(self) -> None:
        result = parse_item(
            {
                "type": ItemType.VIDEO,
                "file_item": {
                    "media": {"encrypt_query_param": "p=1", "aes_key": "k"},
                    "file_name": "report.xlsx",
                },
            }
        )
        assert result is not None
        assert result.type == ItemType.FILE
        assert result.file_item is not None
        assert result.file_item.file_name == "report.xlsx"

    def test_type_file_but_image_item_present(self) -> None:
        result = parse_item(
            {
                "type": ItemType.FILE,
                "image_item": {"url": "https://img.example.com/b.png"},
            }
        )
        assert result is not None
        assert result.type == ItemType.IMAGE
        assert result.image_item is not None
        assert result.image_item.url == "https://img.example.com/b.png"

    def test_type_image_but_text_item_present(self) -> None:
        result = parse_item(
            {
                "type": ItemType.IMAGE,
                "text_item": {"text": "fallback text"},
            }
        )
        assert result is not None
        assert result.type == ItemType.TEXT
        assert result.text_item is not None
        assert result.text_item.text == "fallback text"

    def test_type_text_but_voice_item_present(self) -> None:
        result = parse_item(
            {
                "type": ItemType.TEXT,
                "voice_item": {
                    "media": {"encrypt_query_param": "v=1", "aes_key": "vk"},
                },
            }
        )
        assert result is not None
        assert result.type == ItemType.VOICE
        assert result.voice_item is not None

    def test_no_matching_subkey_returns_none(self) -> None:
        result = parse_item({"type": ItemType.VIDEO, "video_item": {}})
        assert result is None

    def test_fallback_prefers_first_valid_subkey(self) -> None:
        result = parse_item(
            {
                "type": ItemType.VIDEO,
                "text_item": {"text": "hi"},
                "file_item": {
                    "media": {"encrypt_query_param": "p=1", "aes_key": "k"},
                    "file_name": "a.bin",
                },
            }
        )
        assert result is not None
        assert result.type == ItemType.TEXT
        assert result.text_item is not None

    def test_fallback_skips_empty_subkey(self) -> None:
        result = parse_item(
            {
                "type": ItemType.VIDEO,
                "image_item": {},
                "file_item": {
                    "media": {"encrypt_query_param": "p=1", "aes_key": "k"},
                },
            }
        )
        assert result is not None
        assert result.type == ItemType.FILE
