"""Unit tests for contact (vCard) enrichment."""

from __future__ import annotations

import dataclasses
from unittest.mock import AsyncMock

import pytest

from app.channels.media.contact_enrichment import (
    _parse_vcard,
    enrich_contact_inbound,
    format_contact_text,
    has_contact_attachment,
)
from app.channels.types import InboundMessage, MediaType
from app.channels.types.messages import MediaAttachment


def _make_msg(
    media: list[MediaAttachment] | None = None,
    content: str = "hello",
    metadata: dict | None = None,
) -> InboundMessage:
    return InboundMessage(
        channel="test",
        sender_id="user1",
        content=content,
        media=media or [],
        metadata=metadata or {},
    )


class TestParseVcard:
    def test_basic_vcard_30(self) -> None:
        vcard = (
            "BEGIN:VCARD\r\n"
            "VERSION:3.0\r\n"
            "FN:John Doe\r\n"
            "TEL;TYPE=CELL:+1234567890\r\n"
            "EMAIL:john@example.com\r\n"
            "ORG:Acme Corp\r\n"
            "TITLE:Engineer\r\n"
            "END:VCARD\r\n"
        )
        result = _parse_vcard(vcard)
        assert result["name"] == "John Doe"
        assert result["phones"] == ["+1234567890"]
        assert result["emails"] == ["john@example.com"]
        assert result["org"] == "Acme Corp"
        assert result["title"] == "Engineer"

    def test_vcard_with_n_field_only(self) -> None:
        vcard = "BEGIN:VCARD\nVERSION:2.1\nN:Smith;Jane;;;\nTEL:555-1234\nEND:VCARD\n"
        result = _parse_vcard(vcard)
        assert result["name"] == "Jane Smith"
        assert result["phones"] == ["555-1234"]

    def test_vcard_with_bom(self) -> None:
        vcard = "\ufeffBEGIN:VCARD\nFN:BOM Test\nEND:VCARD\n"
        result = _parse_vcard(vcard)
        assert result["name"] == "BOM Test"

    def test_empty_vcard(self) -> None:
        result = _parse_vcard("BEGIN:VCARD\nVERSION:3.0\nEND:VCARD\n")
        assert result == {}

    def test_multiple_phones_and_emails(self) -> None:
        vcard = (
            "BEGIN:VCARD\n"
            "FN:Multi\n"
            "TEL:111\n"
            "TEL:222\n"
            "EMAIL:a@b.com\n"
            "EMAIL:c@d.com\n"
            "END:VCARD\n"
        )
        result = _parse_vcard(vcard)
        assert result["phones"] == ["111", "222"]
        assert result["emails"] == ["a@b.com", "c@d.com"]

    def test_vcard_line_folding(self) -> None:
        vcard = "BEGIN:VCARD\r\nFN:Fold\r\n ed Name\r\nEND:VCARD\r\n"
        result = _parse_vcard(vcard)
        assert result["name"] == "Folded Name"

    def test_note_field(self) -> None:
        vcard = "BEGIN:VCARD\nFN:With Note\nNOTE:Some important note\nEND:VCARD\n"
        result = _parse_vcard(vcard)
        assert result["note"] == "Some important note"

    def test_tel_uri_prefix_stripped(self) -> None:
        vcard = "BEGIN:VCARD\nFN:URI\nTEL;VALUE=uri:tel:+44123456\nEND:VCARD\n"
        result = _parse_vcard(vcard)
        assert result["phones"] == ["+44123456"]


class TestHasContactAttachment:
    def test_no_media(self) -> None:
        msg = _make_msg()
        assert has_contact_attachment(msg) is False

    def test_image_only(self) -> None:
        msg = _make_msg(media=[MediaAttachment(media_type=MediaType.IMAGE, url="http://x.com/a.png")])
        assert has_contact_attachment(msg) is False

    def test_contact_present(self) -> None:
        msg = _make_msg(media=[MediaAttachment(media_type=MediaType.CONTACT, path="/tmp/a.vcf")])
        assert has_contact_attachment(msg) is True


class TestFormatContactText:
    def test_full_contact(self) -> None:
        card = {"name": "Jane", "phones": ["+1"], "emails": ["j@x.com"], "org": "Foo", "title": "Dev"}
        text = format_contact_text(card)
        assert "Name: Jane" in text
        assert "Phone: +1" in text
        assert "Email: j@x.com" in text
        assert "Org: Foo" in text
        assert "Title: Dev" in text

    def test_empty_card(self) -> None:
        assert format_contact_text({}) == "<contact>"

    def test_name_only(self) -> None:
        assert format_contact_text({"name": "Bob"}) == "Name: Bob"


class TestEnrichContactInbound:
    @pytest.mark.asyncio
    async def test_no_contact_returns_unchanged(self) -> None:
        msg = _make_msg(media=[MediaAttachment(media_type=MediaType.IMAGE, url="http://x.com/a.png")])
        result = await enrich_contact_inbound(msg, None)
        assert result is msg

    @pytest.mark.asyncio
    async def test_enriches_from_local_file(self, tmp_path) -> None:
        vcf = tmp_path / "test.vcf"
        vcf.write_text("BEGIN:VCARD\nFN:Local Test\nTEL:999\nEND:VCARD\n")
        msg = _make_msg(media=[MediaAttachment(media_type=MediaType.CONTACT, path=str(vcf))])
        result = await enrich_contact_inbound(msg, None)
        assert "contact_cards" in result.metadata
        cards = result.metadata["contact_cards"]
        assert len(cards) == 1
        assert cards[0]["name"] == "Local Test"
        assert cards[0]["phones"] == ["999"]

    @pytest.mark.asyncio
    async def test_skips_missing_file(self) -> None:
        msg = _make_msg(media=[MediaAttachment(media_type=MediaType.CONTACT, path="/nonexistent/x.vcf")])
        result = await enrich_contact_inbound(msg, None)
        assert result.metadata.get("contact_cards") is None
