"""Tests for the PDF coverage disclosure: which delivered pages the text layer could not read."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from myrm_agent_harness.agent.meta_tools.file_ops.utils.pdf_reader import (
    _build_coverage_note,
    _format_page_ranges,
    read_pdf_as_content_blocks,
    unregister_large_doc_ingest_callback,
)
from tests.agent.meta_tools.file_ops.pdf_reader_support import FakeConfig, FakeImage, FakePDFResult


class TestReadPdfCoverageDisclosure:
    def setup_method(self) -> None:
        unregister_large_doc_ingest_callback()

    def teardown_method(self) -> None:
        unregister_large_doc_ingest_callback()

    @pytest.mark.asyncio
    async def test_mixed_document_discloses_pages_the_text_layer_cannot_read(self) -> None:
        """A partly scanned PDF must name the unread pages instead of implying full coverage."""
        executor = AsyncMock()
        executor.read_file_bytes = AsyncMock(return_value=b"bytes")
        mixed = FakePDFResult(
            text="[Page 1]\nreal body text that is long enough to count\n",
            page_count=3,
            parsed_pages=3,
            pages_without_text=[2, 3],
        )
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
                return_value=mixed,
            ),
            patch(
                "myrm_agent_harness.toolkits.file_parsers.pdf.pdf_content_extractor.PDFExtractConfig",
                FakeConfig,
            ),
        ):
            result = await read_pdf_as_content_blocks("/tmp/mixed.pdf", executor, False)

        assert isinstance(result, str)
        assert "[PDF coverage]" in result
        assert "pages 2-3" in result
        assert "real body text" in result

    @pytest.mark.asyncio
    async def test_fully_read_document_carries_no_coverage_note(self) -> None:
        """A document the text layer read end to end must not grow a caveat."""
        executor = AsyncMock()
        executor.read_file_bytes = AsyncMock(return_value=b"bytes")
        clean = FakePDFResult(text="plain text", page_count=3, pages_without_text=[])
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
                return_value=clean,
            ),
            patch(
                "myrm_agent_harness.toolkits.file_parsers.pdf.pdf_content_extractor.PDFExtractConfig",
                FakeConfig,
            ),
        ):
            result = await read_pdf_as_content_blocks("/tmp/clean.pdf", executor, False)

        assert "[PDF coverage]" not in result


class TestPageRangeFormatting:
    """The coverage note's compact page listing."""

    def test_single_and_contiguous_runs(self) -> None:
        assert _format_page_ranges([1]) == "1"
        assert _format_page_ranges([1, 2, 3]) == "1-3"
        assert _format_page_ranges([1, 3]) == "1, 3"

    def test_sorts_and_dedupes_its_input(self) -> None:
        """Page numbers arrive from set arithmetic; an unsorted list must not render as ``5, 1``."""
        assert _format_page_ranges([5, 1]) == "1, 5"
        assert _format_page_ranges([2, 2, 3]) == "2-3"

    def test_empty_input_yields_empty_string(self) -> None:
        assert _format_page_ranges([]) == ""


class TestCoverageNoteWording:
    """The note must describe what is actually in the payload."""

    def test_partial_gap_says_the_text_below_omits_those_pages(self) -> None:
        note = _build_coverage_note(FakePDFResult(text="body", page_count=8, pages_without_text=[4, 5]))

        assert "2 of the 8 delivered pages" in note
        assert "pages 4-5" in note
        assert "The text below omits those pages" in note

    def test_fully_unreadable_document_does_not_promise_text_that_is_absent(self) -> None:
        """With no readable page there is no "text below"; claiming one would be a lie."""
        note = _build_coverage_note(FakePDFResult(text="", page_count=6, pages_without_text=[1, 2, 3, 4, 5, 6]))

        assert "none of the 6 delivered pages have a text layer" in note
        assert "The text below omits" not in note

    def test_denominator_is_the_delivered_window_not_the_document(self) -> None:
        """A windowed read delivered fewer pages, so the total would overstate what was checked."""
        note = _build_coverage_note(
            FakePDFResult(text="body", page_count=60, parsed_pages=20, pages_without_text=[4, 5])
        )

        assert "2 of the 20 delivered pages" in note
        assert "of 60" not in note

    def test_pages_without_a_delivered_image_are_not_promised_as_images(self) -> None:
        """Past the image ceiling a scanned page has no image either; saying otherwise is false."""
        result = FakePDFResult(text="body", page_count=10, parsed_pages=10, pages_without_text=[4, 5, 6])
        result.images = [FakeImage(page_number=4)]

        note = _build_coverage_note(result)

        assert "Content of pages 4 is only available as page images" in note
        assert "pages 5-6 were not delivered at all" in note

    def test_pages_without_any_image_say_delivery_failed(self) -> None:
        result = FakePDFResult(text="body", page_count=10, parsed_pages=10, pages_without_text=[4, 5])
        result.images = []

        note = _build_coverage_note(result)

        assert "were not delivered, so their content is unavailable" in note
        assert "only available as page images" not in note

    def test_no_gap_produces_no_note(self) -> None:
        assert _build_coverage_note(FakePDFResult(text="body", page_count=3)) == ""
