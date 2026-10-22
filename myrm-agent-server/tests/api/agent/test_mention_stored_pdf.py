"""Tests for how a mentioned stored PDF is reported when it yields no text.

A scan without OCR text or a blank PDF parses to an empty string; the mention must
say so instead of claiming the document is too large.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.services.agent.params.mention import _stored_file_part
from app.services.agent.params.models import MentionReferenceRequest

_PDF_SIZE_BYTES = 2048


def _stored_file_service() -> AsyncMock:
    stored = AsyncMock()
    stored.filename = "scan.pdf"
    stored.size = _PDF_SIZE_BYTES
    stored.storage_path = "uploads/file_scan/scan.pdf"

    service = AsyncMock()
    service.get_file_by_id = AsyncMock(return_value=stored)
    service.get_file_content_by_path = AsyncMock(return_value=b"%PDF-1.4")
    return service


async def _mention_stored_pdf(parsed: str | None) -> tuple[str, int]:
    ref = MentionReferenceRequest(type="uploaded_file", file_id="file_scan", label="scan.pdf")
    with (
        patch("app.core.storage.files_service", _stored_file_service()),
        patch("app.services.agent.params.mention._parse_stored_document", AsyncMock(return_value=parsed)),
    ):
        return await _stored_file_part(ref, 0)


class TestStoredPdfWithoutText:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("parsed", ["", None])
    async def test_reports_missing_text_not_size(self, parsed: str | None) -> None:
        part, consumed = await _mention_stored_pdf(parsed)

        assert "No extractable text (2.0KB)" in part
        assert "file_read_tool" in part
        assert "too large" not in part
        assert consumed == 0

    @pytest.mark.asyncio
    async def test_inlines_parsed_text(self) -> None:
        part, consumed = await _mention_stored_pdf("Quarterly report")

        assert "Quarterly report" in part
        assert consumed == len("Quarterly report".encode())
