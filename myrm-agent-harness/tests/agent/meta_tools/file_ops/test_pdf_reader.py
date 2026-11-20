"""Tests for pdf_reader: path detection, the temp-file handoff and the content a read delivers."""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, patch

import pytest

from myrm_agent_harness.agent.meta_tools.file_ops.utils.pdf_reader import (
    _FALLBACK_MAX_CHARS,
    _write_to_temp,
    is_pdf_path,
    read_pdf_as_content_blocks,
    unregister_large_doc_ingest_callback,
)
from tests.agent.meta_tools.file_ops.pdf_reader_support import FakeConfig, FakeImage, FakePDFResult

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
    def setup_method(self) -> None:
        unregister_large_doc_ingest_callback()

    def teardown_method(self) -> None:
        unregister_large_doc_ingest_callback()

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
    async def test_windowed_read_without_wiki_says_that_pages_were_not_read(self) -> None:
        """With no knowledge base to divert to, the window really is all the model gets."""
        executor = AsyncMock()
        executor.read_file_bytes = AsyncMock(return_value=b"bytes")
        large = FakePDFResult(text="body " * 100, page_count=40, parsed_pages=20)
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
                return_value=large,
            ),
            patch(
                "myrm_agent_harness.toolkits.file_parsers.pdf.pdf_content_extractor.PDFExtractConfig",
                FakeConfig,
            ),
        ):
            result = await read_pdf_as_content_blocks("/tmp/large.pdf", executor, False)

        assert isinstance(result, str)
        assert "[Partial Read]" in result
        assert "only the first 20 pages were read" in result
