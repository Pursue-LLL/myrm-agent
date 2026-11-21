"""Tests for pdf_reader: path detection, the temp-file handoff and the content a read delivers."""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.messages.content import ContentBlock

from myrm_agent_harness.agent.meta_tools.file_ops.utils.pdf_reader import (
    _FALLBACK_MAX_CHARS,
    PDF_READ_PAGE_WINDOW,
    STRUCTURE_OUTLINE_MAX_ENTRIES,
    _write_to_temp,
    is_pdf_path,
    read_pdf_as_content_blocks,
)
from tests.agent.meta_tools.file_ops.pdf_reader_support import (
    FakeConfig,
    FakeImage,
    FakePDFResult,
    read_pdf_with_extraction,
)

# The one hint a read carries when the document is longer than the 20-page window.
PARTIAL_READ_HINT = (
    "\n\n[Partial Read] This document has {pages} pages; only the first 20 pages were read and "
    "file_read cannot open the rest. Do not assume what the unread pages contain; "
    "`parse_mode='structure'` lists the headings with their page numbers."
)

# The three shapes a read takes: the PDF text alone, that text ahead of the page images, or
# that text ahead of the vision chain's description of the page images.
_EVERY_DELIVERY = pytest.mark.parametrize(
    ("supports_vision", "with_images", "described_pages"),
    [
        pytest.param(False, False, None, id="text"),
        pytest.param(True, True, None, id="page_images"),
        pytest.param(False, True, "Page 1: a bar chart.", id="described_pages"),
    ],
)


def _text_of(result: str | list[ContentBlock]) -> str:
    """The PDF text of a read: the string itself, or the leading text block ahead of the page content."""
    if isinstance(result, str):
        return result
    first = result[0]
    assert first["type"] == "text"
    return first["text"]


# ---------------------------------------------------------------------------
# is_pdf_path
# ---------------------------------------------------------------------------


class TestIsPdfPath:
    def test_pdf_detected(self) -> None:
        assert is_pdf_path("report.pdf") is True

    def test_pdf_uppercase(self) -> None:
        assert is_pdf_path("REPORT.PDF") is True

    def test_pdf_mixed_case(self) -> None:
        assert is_pdf_path("Report.Pdf") is True

    def test_non_pdf_rejected(self) -> None:
        assert is_pdf_path("report.docx") is False

    def test_no_extension_rejected(self) -> None:
        assert is_pdf_path("report") is False

    def test_nested_path(self) -> None:
        assert is_pdf_path("/tmp/docs/report.pdf") is True

    def test_dot_pdf_in_dirname_not_detected(self) -> None:
        assert is_pdf_path("/tmp/pdf.dir/readme.txt") is False

    def test_hidden_pdf_file(self) -> None:
        assert is_pdf_path("/tmp/.hidden.pdf") is True


# ---------------------------------------------------------------------------
# _write_to_temp
# ---------------------------------------------------------------------------


class TestWriteToTemp:
    @pytest.mark.asyncio
    async def test_roundtrip(self) -> None:
        content = b"hello pdf bytes"
        tmp = await _write_to_temp(content)
        try:
            with open(tmp, "rb") as f:
                assert f.read() == content
            assert tmp.endswith(".pdf")
        finally:
            os.unlink(tmp)


# ---------------------------------------------------------------------------
# read_pdf_as_content_blocks
# ---------------------------------------------------------------------------


class TestReadPdfAsContentBlocks:
    @pytest.mark.asyncio
    async def test_file_not_found_propagates(self) -> None:
        executor = AsyncMock()
        executor.read_file_bytes = AsyncMock(side_effect=FileNotFoundError("gone"))
        with pytest.raises(FileNotFoundError):
            await read_pdf_as_content_blocks("/tmp/missing.pdf", executor, False)

    @pytest.mark.asyncio
    async def test_read_bytes_generic_error(self) -> None:
        executor = AsyncMock()
        executor.read_file_bytes = AsyncMock(side_effect=OSError("disk"))
        result = await read_pdf_as_content_blocks("/tmp/bad.pdf", executor, False)
        assert "Failed to read" in result

    @pytest.mark.asyncio
    async def test_import_error_graceful(self) -> None:
        executor = AsyncMock()
        executor.read_file_bytes = AsyncMock(return_value=b"bytes")
        with (
            patch(
                "myrm_agent_harness.agent.meta_tools.file_ops.utils.pdf_reader._write_to_temp",
                new_callable=AsyncMock,
                return_value="/tmp/t.pdf",
            ),
            patch("os.unlink"),
            patch.dict(
                "sys.modules",
                {"myrm_agent_harness.toolkits.file_parsers.pdf.pdf_content_extractor": None},
            ),
        ):
            result = await read_pdf_as_content_blocks("/tmp/test.pdf", executor, False)
        assert "not available" in result

    @pytest.mark.asyncio
    async def test_extraction_failure(self) -> None:
        executor = AsyncMock()
        executor.read_file_bytes = AsyncMock(return_value=b"bytes")
        with (
            patch(
                "myrm_agent_harness.agent.meta_tools.file_ops.utils.pdf_reader._write_to_temp",
                new_callable=AsyncMock,
                return_value="/tmp/t.pdf",
            ),
            patch("os.unlink"),
            patch(
                "myrm_agent_harness.toolkits.file_parsers.pdf.pdf_content_extractor.extract_pdf_content",
                new_callable=AsyncMock,
                side_effect=RuntimeError("extract fail"),
            ),
        ):
            result = await read_pdf_as_content_blocks("/tmp/test.pdf", executor, False)
        assert "Extraction failed" in result

    @pytest.mark.asyncio
    async def test_empty_content_encrypted(self) -> None:
        executor = AsyncMock()
        executor.read_file_bytes = AsyncMock(return_value=b"bytes")
        empty_result = FakePDFResult(text="   ", page_count=1)
        with (
            patch(
                "myrm_agent_harness.agent.meta_tools.file_ops.utils.pdf_reader._write_to_temp",
                new_callable=AsyncMock,
                return_value="/tmp/t.pdf",
            ),
            patch("os.unlink"),
            patch(
                "myrm_agent_harness.toolkits.file_parsers.pdf.pdf_content_extractor.extract_pdf_content",
                new_callable=AsyncMock,
                return_value=empty_result,
            ),
            patch(
                "myrm_agent_harness.toolkits.file_parsers.pdf.pdf_content_extractor.PDFExtractConfig",
                FakeConfig,
            ),
        ):
            result = await read_pdf_as_content_blocks("/tmp/enc.pdf", executor, False)
        assert "encrypted" in result

    @pytest.mark.asyncio
    async def test_text_truncation(self) -> None:
        executor = AsyncMock()
        executor.read_file_bytes = AsyncMock(return_value=b"bytes")
        long_text = "x" * (_FALLBACK_MAX_CHARS + 1000)
        big_result = FakePDFResult(text=long_text, page_count=5)
        with (
            patch(
                "myrm_agent_harness.agent.meta_tools.file_ops.utils.pdf_reader._write_to_temp",
                new_callable=AsyncMock,
                return_value="/tmp/t.pdf",
            ),
            patch("os.unlink"),
            patch(
                "myrm_agent_harness.toolkits.file_parsers.pdf.pdf_content_extractor.extract_pdf_content",
                new_callable=AsyncMock,
                return_value=big_result,
            ),
            patch(
                "myrm_agent_harness.toolkits.file_parsers.pdf.pdf_content_extractor.PDFExtractConfig",
                FakeConfig,
            ),
        ):
            result = await read_pdf_as_content_blocks("/tmp/big.pdf", executor, False)
        assert f"truncated at {_FALLBACK_MAX_CHARS}" in result

    @pytest.mark.asyncio
    async def test_vision_mode_returns_blocks(self) -> None:
        executor = AsyncMock()
        executor.read_file_bytes = AsyncMock(return_value=b"bytes")
        img = FakeImage()
        vision_result = FakePDFResult(text="Visual text", page_count=3, images=[img])
        with (
            patch(
                "myrm_agent_harness.agent.meta_tools.file_ops.utils.pdf_reader._write_to_temp",
                new_callable=AsyncMock,
                return_value="/tmp/t.pdf",
            ),
            patch("os.unlink"),
            patch(
                "myrm_agent_harness.toolkits.file_parsers.pdf.pdf_content_extractor.extract_pdf_content",
                new_callable=AsyncMock,
                return_value=vision_result,
            ),
            patch(
                "myrm_agent_harness.toolkits.file_parsers.pdf.pdf_content_extractor.PDFExtractConfig",
                FakeConfig,
            ),
        ):
            result = await read_pdf_as_content_blocks("/tmp/v.pdf", executor, True)
        assert isinstance(result, list)
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_text_only_no_images_returns_string(self) -> None:
        executor = AsyncMock()
        executor.read_file_bytes = AsyncMock(return_value=b"bytes")
        text_result = FakePDFResult(text="Plain text", page_count=3)
        with (
            patch(
                "myrm_agent_harness.agent.meta_tools.file_ops.utils.pdf_reader._write_to_temp",
                new_callable=AsyncMock,
                return_value="/tmp/t.pdf",
            ),
            patch("os.unlink"),
            patch(
                "myrm_agent_harness.toolkits.file_parsers.pdf.pdf_content_extractor.extract_pdf_content",
                new_callable=AsyncMock,
                return_value=text_result,
            ),
            patch(
                "myrm_agent_harness.toolkits.file_parsers.pdf.pdf_content_extractor.PDFExtractConfig",
                FakeConfig,
            ),
        ):
            result = await read_pdf_as_content_blocks("/tmp/txt.pdf", executor, False)
        assert isinstance(result, str)
        assert "Plain text" in result

    @pytest.mark.asyncio
    async def test_no_text_image_only_returns_fallback(self) -> None:
        """PDF with no text and not supporting vision returns image-only message."""
        executor = AsyncMock()
        executor.read_file_bytes = AsyncMock(return_value=b"bytes")
        img_only = FakePDFResult(text="   ", page_count=3, images=[FakeImage()])
        with (
            patch(
                "myrm_agent_harness.agent.meta_tools.file_ops.utils.pdf_reader._write_to_temp",
                new_callable=AsyncMock,
                return_value="/tmp/t.pdf",
            ),
            patch("os.unlink"),
            patch(
                "myrm_agent_harness.toolkits.file_parsers.pdf.pdf_content_extractor.extract_pdf_content",
                new_callable=AsyncMock,
                return_value=img_only,
            ),
            patch(
                "myrm_agent_harness.toolkits.file_parsers.pdf.pdf_content_extractor.PDFExtractConfig",
                FakeConfig,
            ),
        ):
            result = await read_pdf_as_content_blocks("/tmp/img.pdf", executor, False)
        assert "image-only" in result

    @pytest.mark.asyncio
    async def test_a_document_that_fits_the_window_carries_no_partial_read_hint(self) -> None:
        result = await read_pdf_with_extraction(FakePDFResult(text="Hello world", page_count=20))

        assert "Hello world" in result
        assert "[Partial Read]" not in result

    @pytest.mark.asyncio
    async def test_partial_read_hint_states_the_coverage_and_points_to_the_outline(self) -> None:
        """It says what was read, promises no way to read on, and names the one tool that lists the rest."""
        result = await read_pdf_with_extraction(FakePDFResult(text="body " * 100, page_count=40, parsed_pages=20))

        assert isinstance(result, str)
        assert result.endswith(PARTIAL_READ_HINT.format(pages=40))

    @pytest.mark.asyncio
    @pytest.mark.parametrize("page_count", [21, 2000, 2001, 5000])
    async def test_the_hint_does_not_change_with_the_length_of_the_document(self, page_count: int) -> None:
        """No page count has a wording of its own, and none of them mentions a knowledge base."""
        result = await read_pdf_with_extraction(FakePDFResult(text="body", page_count=page_count, parsed_pages=20))

        assert isinstance(result, str)
        assert result.endswith(PARTIAL_READ_HINT.format(pages=page_count))
        assert "wiki" not in result.lower()
        assert "index" not in result.lower()

    @pytest.mark.asyncio
    @_EVERY_DELIVERY
    async def test_every_delivery_shape_ends_its_text_with_the_partial_read_hint(
        self, supports_vision: bool, with_images: bool, described_pages: str | None
    ) -> None:
        """However the pages reach the model, a document longer than the window says the rest was not read."""
        pdf = FakePDFResult(text="body", page_count=40, parsed_pages=20, images=[FakeImage()] if with_images else [])

        result = await read_pdf_with_extraction(pdf, supports_vision=supports_vision, described_pages=described_pages)

        assert _text_of(result).endswith(PARTIAL_READ_HINT.format(pages=40))

    @pytest.mark.asyncio
    @_EVERY_DELIVERY
    async def test_no_delivery_shape_carries_the_hint_for_a_document_that_fits_the_window(
        self, supports_vision: bool, with_images: bool, described_pages: str | None
    ) -> None:
        pdf = FakePDFResult(text="body", page_count=20, images=[FakeImage()] if with_images else [])

        result = await read_pdf_with_extraction(pdf, supports_vision=supports_vision, described_pages=described_pages)

        assert "[Partial Read]" not in _text_of(result)

    @pytest.mark.asyncio
    async def test_the_extractor_is_asked_for_exactly_the_window_the_hint_speaks_of(self) -> None:
        """A wider window would hand the model pages that the hint says were not read."""
        extractor = AsyncMock()

        await read_pdf_with_extraction(FakePDFResult(text="body", page_count=40, parsed_pages=20), extractor=extractor)

        assert extractor.await_args.args[1].max_pages == PDF_READ_PAGE_WINDOW

    @pytest.mark.asyncio
    async def test_structure_outline_past_the_entry_cap_only_counts_the_omitted_headings(self) -> None:
        from myrm_agent_harness.toolkits.file_parsers.base import PDFHeading, PDFParseResult

        executor = AsyncMock()
        executor.read_file_bytes = AsyncMock(return_value=b"%PDF-1.4 mock")
        omitted = 50
        headings = [
            PDFHeading(level=1, title=f"Section {n}", page_num=n)
            for n in range(1, STRUCTURE_OUTLINE_MAX_ENTRIES + omitted + 1)
        ]
        parsed = PDFParseResult(text="", tables=[], metadata={"page_count": 300}, headings=headings)

        with patch("myrm_agent_harness.toolkits.file_parsers.pdf.pdf.PDFPlumberParser.parse_sync", return_value=parsed):
            outline = await read_pdf_as_content_blocks("/tmp/long.pdf", executor, False, parse_mode="structure")

        assert isinstance(outline, str)
        assert f"Page {STRUCTURE_OUTLINE_MAX_ENTRIES}: Section {STRUCTURE_OUTLINE_MAX_ENTRIES}" in outline
        assert f"Section {STRUCTURE_OUTLINE_MAX_ENTRIES + 1}" not in outline
        assert outline.endswith(f"… ({omitted} more headings omitted)")
        assert "wiki" not in outline.lower()
