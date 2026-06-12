"""Unit tests for contact (vCard) enrichment."""

from __future__ import annotations

import pytest

from app.channels.media.contact_enrichment import (
    MAX_CONTACTS_PER_MESSAGE,
    _parse_vcard,
    enrich_contact_inbound,
    format_contact_text,
    has_contact_attachment,
)
from app.channels.types import InboundMessage, MediaType
from app.channels.types.messages import MediaAttachment, guess_media_type


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

    def test_adr_field(self) -> None:
        vcard = "BEGIN:VCARD\nFN:Addr Test\nADR;TYPE=WORK:;;123 Main St;Springfield;IL;62701;US\nEND:VCARD\n"
        result = _parse_vcard(vcard)
        assert result["address"] == "123 Main St, Springfield, IL, 62701, US"

    def test_url_field(self) -> None:
        vcard = "BEGIN:VCARD\nFN:URL Test\nURL:https://example.com\nEND:VCARD\n"
        result = _parse_vcard(vcard)
        assert result["url"] == "https://example.com"

    def test_bday_field(self) -> None:
        vcard = "BEGIN:VCARD\nFN:Bday Test\nBDAY:1990-05-15\nEND:VCARD\n"
        result = _parse_vcard(vcard)
        assert result["birthday"] == "1990-05-15"

    def test_crlf_no_double_newlines(self) -> None:
        vcard = "BEGIN:VCARD\r\nFN:CRLF Test\r\nTEL:999\r\nEND:VCARD\r\n"
        result = _parse_vcard(vcard)
        assert result["name"] == "CRLF Test"
        assert result["phones"] == ["999"]

    def test_apple_item_prefix(self) -> None:
        """Apple vCards use item1.TEL, item2.EMAIL style prefixes."""
        vcard = (
            "BEGIN:VCARD\n"
            "FN:Apple User\n"
            "item1.TEL:+1-555-0100\n"
            "item2.EMAIL:apple@icloud.com\n"
            "item1.X-ABLabel:mobile\n"
            "END:VCARD\n"
        )
        result = _parse_vcard(vcard)
        assert result["name"] == "Apple User"
        assert "+1-555-0100" in result["phones"]
        assert "apple@icloud.com" in result["emails"]

    def test_escaped_characters(self) -> None:
        """vCard escape sequences: \\n \\, \\;"""
        vcard = "BEGIN:VCARD\nFN:Escape Test\nNOTE:Line1\\nLine2\\, with comma\\; semi\nEND:VCARD\n"
        result = _parse_vcard(vcard)
        assert "Line1 Line2, with comma; semi" == result["note"]

    def test_vcard_21_without_fn(self) -> None:
        """vCard 2.1 may only have N field, no FN."""
        vcard = "BEGIN:VCARD\nVERSION:2.1\nN:Doe;John;Q;Mr;Jr\nEND:VCARD\n"
        result = _parse_vcard(vcard)
        assert "John" in result["name"]
        assert "Doe" in result["name"]

    def test_org_with_semicolons(self) -> None:
        """ORG may contain department hierarchy separated by semicolons."""
        vcard = "BEGIN:VCARD\nFN:Org Test\nORG:Acme Corp;Engineering;AI Team\nEND:VCARD\n"
        result = _parse_vcard(vcard)
        assert "Acme Corp" in result["org"]
        assert "Engineering" in result["org"]
        assert "AI Team" in result["org"]

    def test_mixed_line_endings(self) -> None:
        """File with mixed \\r\\n and \\n endings."""
        vcard = "BEGIN:VCARD\r\nFN:Mixed\nTEL:123\r\nEMAIL:m@x.com\nEND:VCARD\r\n"
        result = _parse_vcard(vcard)
        assert result["name"] == "Mixed"
        assert result["phones"] == ["123"]
        assert result["emails"] == ["m@x.com"]

    def test_tab_line_folding(self) -> None:
        """RFC allows TAB as line folding continuation marker."""
        vcard = "BEGIN:VCARD\r\nFN:Tab\r\n\tFolded\r\nEND:VCARD\r\n"
        result = _parse_vcard(vcard)
        assert result["name"] == "TabFolded"

    def test_garbage_text_returns_empty(self) -> None:
        result = _parse_vcard("this is not a vcard at all")
        assert result == {}


class TestGuessMediaTypeVcard:
    """Test guess_media_type for vCard MIME types and extensions."""

    def test_text_vcard_mime(self) -> None:
        assert guess_media_type("file.txt", "text/vcard") == MediaType.CONTACT

    def test_text_x_vcard_mime(self) -> None:
        assert guess_media_type("file.txt", "text/x-vcard") == MediaType.CONTACT

    def test_text_directory_mime(self) -> None:
        assert guess_media_type("file.txt", "text/directory") == MediaType.CONTACT

    def test_application_vcard_mime(self) -> None:
        assert guess_media_type("file.txt", "application/vcard") == MediaType.CONTACT

    def test_application_x_vcard_mime(self) -> None:
        assert guess_media_type("file.txt", "application/x-vcard") == MediaType.CONTACT

    def test_vcf_extension_no_mime(self) -> None:
        assert guess_media_type("contact.vcf") == MediaType.CONTACT

    def test_vcf_extension_uppercase(self) -> None:
        assert guess_media_type("CONTACT.VCF") == MediaType.CONTACT

    def test_non_vcard_remains_document(self) -> None:
        assert guess_media_type("file.pdf", "application/pdf") == MediaType.DOCUMENT


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

    def test_mixed_media_detects_contact(self) -> None:
        msg = _make_msg(media=[
            MediaAttachment(media_type=MediaType.IMAGE, url="http://x.com/a.png"),
            MediaAttachment(media_type=MediaType.CONTACT, path="/tmp/a.vcf"),
        ])
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

    def test_all_fields(self) -> None:
        card = {
            "name": "Full",
            "phones": ["+1", "+2"],
            "emails": ["a@b.com"],
            "org": "Org",
            "title": "CEO",
            "note": "VIP",
            "address": "123 St",
            "url": "https://x.com",
            "birthday": "2000-01-01",
        }
        text = format_contact_text(card)
        assert "Phone: +1, +2" in text
        assert "Address: 123 St" in text
        assert "URL: https://x.com" in text
        assert "Birthday: 2000-01-01" in text
        assert "Note: VIP" in text


class TestEnrichContactInbound:
    @pytest.mark.asyncio
    async def test_no_contact_returns_unchanged(self) -> None:
        msg = _make_msg(media=[MediaAttachment(media_type=MediaType.IMAGE, url="http://x.com/a.png")])
        result = await enrich_contact_inbound(msg)
        assert result is msg

    @pytest.mark.asyncio
    async def test_enriches_from_local_file(self, tmp_path) -> None:
        vcf = tmp_path / "test.vcf"
        vcf.write_text("BEGIN:VCARD\nFN:Local Test\nTEL:999\nEND:VCARD\n")
        msg = _make_msg(media=[MediaAttachment(media_type=MediaType.CONTACT, path=str(vcf))])
        result = await enrich_contact_inbound(msg)
        assert "contact_cards" in result.metadata
        cards = result.metadata["contact_cards"]
        assert len(cards) == 1
        assert cards[0]["name"] == "Local Test"
        assert cards[0]["phones"] == ["999"]

    @pytest.mark.asyncio
    async def test_skips_missing_file(self) -> None:
        msg = _make_msg(media=[MediaAttachment(media_type=MediaType.CONTACT, path="/nonexistent/x.vcf")])
        result = await enrich_contact_inbound(msg)
        assert result.metadata.get("contact_cards") is None

    @pytest.mark.asyncio
    async def test_immutability(self, tmp_path) -> None:
        """Original message must not be mutated."""
        vcf = tmp_path / "immutable.vcf"
        vcf.write_text("BEGIN:VCARD\nFN:Immutable\nTEL:111\nEND:VCARD\n")
        msg = _make_msg(media=[MediaAttachment(media_type=MediaType.CONTACT, path=str(vcf))])
        original_metadata = dict(msg.metadata)
        result = await enrich_contact_inbound(msg)
        assert result is not msg
        assert msg.metadata == original_metadata

    @pytest.mark.asyncio
    async def test_max_contacts_limit(self, tmp_path) -> None:
        """Only MAX_CONTACTS_PER_MESSAGE contacts are processed."""
        attachments = []
        for i in range(MAX_CONTACTS_PER_MESSAGE + 3):
            vcf = tmp_path / f"contact_{i}.vcf"
            vcf.write_text(f"BEGIN:VCARD\nFN:Person {i}\nTEL:{i}\nEND:VCARD\n")
            attachments.append(MediaAttachment(media_type=MediaType.CONTACT, path=str(vcf)))
        msg = _make_msg(media=attachments)
        result = await enrich_contact_inbound(msg)
        cards = result.metadata["contact_cards"]
        assert len(cards) == MAX_CONTACTS_PER_MESSAGE

    @pytest.mark.asyncio
    async def test_oversized_file_skipped(self, tmp_path) -> None:
        """Files exceeding MAX_VCARD_BYTES are silently skipped."""
        from app.channels.media.contact_enrichment import MAX_VCARD_BYTES

        vcf = tmp_path / "huge.vcf"
        vcf.write_text("BEGIN:VCARD\nFN:Huge\nNOTE:" + "x" * (MAX_VCARD_BYTES + 100) + "\nEND:VCARD\n")
        msg = _make_msg(media=[MediaAttachment(media_type=MediaType.CONTACT, path=str(vcf))])
        result = await enrich_contact_inbound(msg)
        assert result.metadata.get("contact_cards") is None

    @pytest.mark.asyncio
    async def test_preserves_existing_metadata(self, tmp_path) -> None:
        """Existing metadata keys are preserved after enrichment."""
        vcf = tmp_path / "preserve.vcf"
        vcf.write_text("BEGIN:VCARD\nFN:Keep Meta\nEND:VCARD\n")
        msg = _make_msg(
            media=[MediaAttachment(media_type=MediaType.CONTACT, path=str(vcf))],
            metadata={"existing_key": "keep_me"},
        )
        result = await enrich_contact_inbound(msg)
        assert result.metadata["existing_key"] == "keep_me"
        assert "contact_cards" in result.metadata
