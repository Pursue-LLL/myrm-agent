"""Tests for document_enrichment — PDF/Office download and text injection."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from app.channels.media.document_enrichment import (
    enrich_document_inbound,
    has_document_attachment,
)
from app.channels.types import InboundMessage, MediaAttachment, MediaType
from app.core.channel_bridge.agent_executor.helpers import build_channel_inbound_query


def _make_msg(
    *,
    media: tuple[MediaAttachment, ...] = (),
    metadata: dict[str, object] | None = None,
    content: str = "summarize this",
) -> InboundMessage:
    return InboundMessage(
        channel="telegram",
        sender_id="u1",
        content=content,
        sent_at=1.0,
        sent_timezone="UTC",
        chat_id="c1",
        user_id="u1",
        is_group=False,
        mentioned=False,
        media=media,
        metadata=metadata or {},
    )


class TestHasDocumentAttachment:
    def test_no_media(self) -> None:
        assert has_document_attachment(_make_msg()) is False

    def test_image_only(self) -> None:
        msg = _make_msg(media=(MediaAttachment(media_type=MediaType.IMAGE),))
        assert has_document_attachment(msg) is False

    def test_zip_document_counts_as_document(self) -> None:
        msg = _make_msg(
            media=(
                MediaAttachment(
                    media_type=MediaType.DOCUMENT,
                    filename="archive.zip",
                ),
            )
        )
        assert has_document_attachment(msg) is True

    def test_pdf_document(self) -> None:
        msg = _make_msg(
            media=(
                MediaAttachment(
                    media_type=MediaType.DOCUMENT,
                    path="/tmp/report.pdf",
                    filename="report.pdf",
                    mime_type="application/pdf",
                ),
            )
        )
        assert has_document_attachment(msg) is True


class TestEnrichDocumentInbound:
    @pytest.mark.asyncio
    async def test_zip_reference_when_not_extractable(self) -> None:
        msg = _make_msg(
            media=(
                MediaAttachment(
                    media_type=MediaType.DOCUMENT,
                    filename="archive.zip",
                ),
            )
        )
        result = await enrich_document_inbound(msg, None, extract_enabled=True)
        blocks = result.metadata.get("document_text_blocks")
        assert isinstance(blocks, list)
        assert blocks[0]["text"] == "[Attachment: archive.zip]"

    @pytest.mark.asyncio
    async def test_extract_disabled_reference_only(self) -> None:
        msg = _make_msg(
            media=(
                MediaAttachment(
                    media_type=MediaType.DOCUMENT,
                    path="/tmp/report.pdf",
                    filename="report.pdf",
                ),
            )
        )
        result = await enrich_document_inbound(msg, None, extract_enabled=False)
        blocks = result.metadata.get("document_text_blocks")
        assert isinstance(blocks, list)
        assert blocks[0]["text"] == "[Attachment: report.pdf]"

    @pytest.mark.asyncio
    async def test_extract_enabled_uses_content_extraction(self) -> None:
        msg = _make_msg(
            media=(
                MediaAttachment(
                    media_type=MediaType.DOCUMENT,
                    path="/tmp/spec.docx",
                    filename="spec.docx",
                ),
            )
        )
        with (
            patch(
                "app.channels.media.document_enrichment._download_document_bytes",
                new_callable=AsyncMock,
                return_value=b"doc-bytes",
            ),
            patch(
                "app.channels.media.document_enrichment._extract_text_from_bytes",
                new_callable=AsyncMock,
                return_value="contract terms here",
            ),
        ):
            result = await enrich_document_inbound(msg, None, extract_enabled=True)

        blocks = result.metadata.get("document_text_blocks")
        assert isinstance(blocks, list)
        assert "contract terms here" in blocks[0]["text"]
        assert "spec.docx" in blocks[0]["text"]


class TestEnrichDocumentLocalFile:
    @pytest.mark.asyncio
    async def test_local_pdf_extracts_via_harness(self, tmp_path: Path) -> None:
        pdf_path = tmp_path / "note.pdf"
        pdf_path.write_bytes(
            b"%PDF-1.4\n"
            b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
            b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
            b"3 0 obj<</Type/Page/MediaBox[0 0 200 200]/Parent 2 0 R"
            b"/Contents 4 0 R>>endobj\n"
            b"4 0 obj<</Length 21>>stream\n"
            b"BT /F1 12 Tf ET\n"
            b"endstream\nendobj\n"
            b"xref\n0 5\n"
            b"trailer<</Size 5/Root 1 0 R>>\n"
            b"startxref\n0\n%%EOF\n"
        )
        msg = _make_msg(
            media=(
                MediaAttachment(
                    media_type=MediaType.DOCUMENT,
                    path=str(pdf_path),
                    filename="note.pdf",
                    mime_type="application/pdf",
                ),
            ),
        )
        result = await enrich_document_inbound(msg, None, extract_enabled=True)
        blocks = result.metadata.get("document_text_blocks")
        assert isinstance(blocks, list)
        assert len(blocks) == 1


class TestBuildChannelInboundQueryDocuments:
    def test_document_blocks_appended_to_text(self) -> None:
        msg = _make_msg(
            metadata={
                "document_text_blocks": [
                    {"filename": "a.pdf", "text": "## Attachment: a.pdf\nline one"},
                ],
            },
        )
        out = build_channel_inbound_query(msg)
        assert isinstance(out, str)
        assert "line one" in out
        assert "summarize this" in out
