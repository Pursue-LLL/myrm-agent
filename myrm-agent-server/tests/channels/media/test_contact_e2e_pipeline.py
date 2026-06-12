"""End-to-end pipeline test: vCard file → enrichment → build_channel_inbound_query.

Verifies the full data flow without mocking the enrichment or query builder.
"""

from __future__ import annotations

import pytest

from app.channels.media.contact_enrichment import enrich_contact_inbound
from app.channels.types import InboundMessage, MediaType
from app.channels.types.messages import MediaAttachment
from app.core.channel_bridge.agent_executor.helpers import build_channel_inbound_query


def _make_msg(
    media: list[MediaAttachment] | None = None,
    content: str = "Please save this contact",
    metadata: dict | None = None,
) -> InboundMessage:
    return InboundMessage(
        channel="imessage",
        sender_id="user1",
        content=content,
        media=media or [],
        metadata=metadata or {},
    )


SAMPLE_VCARD = (
    "BEGIN:VCARD\r\n"
    "VERSION:3.0\r\n"
    "FN:Alice Wang\r\n"
    "N:Wang;Alice;;;\r\n"
    "TEL;TYPE=CELL:+86 138 0000 1234\r\n"
    "TEL;TYPE=WORK:+86 10 8888 7777\r\n"
    "EMAIL:alice@example.com\r\n"
    "ORG:Myrm AI\r\n"
    "TITLE:CTO\r\n"
    "ADR;TYPE=WORK:;;100 Main St;Beijing;;100000;China\r\n"
    "URL:https://myrm.ai\r\n"
    "BDAY:1990-05-15\r\n"
    "NOTE:VIP customer\r\n"
    "END:VCARD\r\n"
)


class TestContactPipelineE2E:
    """Full pipeline: vCard file → enrich → query builder → LLM text."""

    @pytest.mark.asyncio
    async def test_single_contact_full_pipeline(self, tmp_path) -> None:
        vcf = tmp_path / "alice.vcf"
        vcf.write_text(SAMPLE_VCARD)

        msg = _make_msg(media=[MediaAttachment(media_type=MediaType.CONTACT, path=str(vcf))])

        enriched = await enrich_contact_inbound(msg)

        assert "contact_cards" in enriched.metadata
        cards = enriched.metadata["contact_cards"]
        assert len(cards) == 1
        card = cards[0]
        assert card["name"] == "Alice Wang"
        assert "+86 138 0000 1234" in card["phones"]
        assert "+86 10 8888 7777" in card["phones"]
        assert card["emails"] == ["alice@example.com"]
        assert card["org"] == "Myrm AI"
        assert card["title"] == "CTO"
        assert "Beijing" in card["address"]
        assert card["url"] == "https://myrm.ai"
        assert card["birthday"] == "1990-05-15"

        query = build_channel_inbound_query(enriched)
        assert isinstance(query, str)
        assert "[Shared Contact]" in query
        assert "Alice Wang" in query
        assert "+86 138 0000 1234" in query
        assert "alice@example.com" in query
        assert "Myrm AI" in query
        assert "CTO" in query
        assert "Beijing" in query
        assert "https://myrm.ai" in query
        assert "1990-05-15" in query
        assert "VIP customer" in query

    @pytest.mark.asyncio
    async def test_multiple_contacts_full_pipeline(self, tmp_path) -> None:
        vcf1 = tmp_path / "bob.vcf"
        vcf1.write_text("BEGIN:VCARD\nFN:Bob\nTEL:111\nEND:VCARD\n")
        vcf2 = tmp_path / "carol.vcf"
        vcf2.write_text("BEGIN:VCARD\nFN:Carol\nEMAIL:carol@x.com\nEND:VCARD\n")

        msg = _make_msg(media=[
            MediaAttachment(media_type=MediaType.CONTACT, path=str(vcf1)),
            MediaAttachment(media_type=MediaType.CONTACT, path=str(vcf2)),
        ])

        enriched = await enrich_contact_inbound(msg)
        cards = enriched.metadata["contact_cards"]
        assert len(cards) == 2

        query = build_channel_inbound_query(enriched)
        assert "[Shared Contacts]" in query
        assert "Bob" in query
        assert "111" in query
        assert "Carol" in query
        assert "carol@x.com" in query

    @pytest.mark.asyncio
    async def test_no_contact_passthrough(self) -> None:
        msg = _make_msg(media=[MediaAttachment(media_type=MediaType.IMAGE, url="http://x.com/a.png")])

        enriched = await enrich_contact_inbound(msg)
        assert enriched is msg

        query = build_channel_inbound_query(enriched)
        assert isinstance(query, str)
        assert "[Shared Contact]" not in query

    @pytest.mark.asyncio
    async def test_contact_with_document_coexist(self, tmp_path) -> None:
        vcf = tmp_path / "dan.vcf"
        vcf.write_text("BEGIN:VCARD\nFN:Dan\nTEL:222\nEND:VCARD\n")

        msg = _make_msg(
            media=[MediaAttachment(media_type=MediaType.CONTACT, path=str(vcf))],
            metadata={"document_text_blocks": [{"text": "Quarterly report summary."}]},
        )

        enriched = await enrich_contact_inbound(msg)

        query = build_channel_inbound_query(enriched)
        assert "Quarterly report summary." in query
        assert "[Shared Contact]" in query
        assert "Dan" in query
