"""Tests for the PDF large-document auto-ingest: callback registry, background ingest and its read hints."""

from __future__ import annotations

import asyncio
import hashlib
from unittest.mock import AsyncMock, patch

import pytest

from myrm_agent_harness.agent.meta_tools.file_ops.utils.pdf_reader import (
    RAG_MAX_PAGES_LIMIT,
    RAG_PAGE_THRESHOLD,
    _fire_and_forget_ingest,
    _schedule_rag_ingest,
    read_pdf_as_content_blocks,
    register_large_doc_ingest_callback,
    unregister_large_doc_ingest_callback,
)
from tests.agent.meta_tools.file_ops.pdf_reader_support import FakeConfig, FakePDFResult

# ---------------------------------------------------------------------------
# Callback registration
# ---------------------------------------------------------------------------


class TestCallbackRegistration:
    def setup_method(self) -> None:
        unregister_large_doc_ingest_callback()

    def teardown_method(self) -> None:
        unregister_large_doc_ingest_callback()

    def test_register_and_unregister(self) -> None:
        cb = AsyncMock()
        register_large_doc_ingest_callback(cb)
        from myrm_agent_harness.agent.meta_tools.file_ops.utils import pdf_reader

        assert pdf_reader._ingest_callback is cb
        unregister_large_doc_ingest_callback()
        assert pdf_reader._ingest_callback is None

    def test_register_replaces_previous(self) -> None:
        cb1 = AsyncMock()
        cb2 = AsyncMock()
        register_large_doc_ingest_callback(cb1)
        register_large_doc_ingest_callback(cb2)
        from myrm_agent_harness.agent.meta_tools.file_ops.utils import pdf_reader

        assert pdf_reader._ingest_callback is cb2

    def test_double_unregister_is_safe(self) -> None:
        unregister_large_doc_ingest_callback()
        unregister_large_doc_ingest_callback()


# ---------------------------------------------------------------------------
# _fire_and_forget_ingest
# ---------------------------------------------------------------------------


class TestFireAndForgetIngest:
    def setup_method(self) -> None:
        unregister_large_doc_ingest_callback()

    def teardown_method(self) -> None:
        unregister_large_doc_ingest_callback()

    @pytest.mark.asyncio
    async def test_no_callback_noop(self) -> None:
        await _fire_and_forget_ingest("test.pdf", "text", "hash123")

    @pytest.mark.asyncio
    async def test_callback_called(self) -> None:
        cb = AsyncMock()
        register_large_doc_ingest_callback(cb)
        await _fire_and_forget_ingest("test.pdf", "full text", "abc123")
        cb.assert_awaited_once_with("test.pdf", "full text", "abc123")

    @pytest.mark.asyncio
    async def test_callback_exception_swallowed(self) -> None:
        cb = AsyncMock(side_effect=RuntimeError("boom"))
        register_large_doc_ingest_callback(cb)
        await _fire_and_forget_ingest("test.pdf", "text", "hash")


# ---------------------------------------------------------------------------
# _schedule_rag_ingest
# ---------------------------------------------------------------------------


class TestScheduleRagIngest:
    def setup_method(self) -> None:
        unregister_large_doc_ingest_callback()

    def teardown_method(self) -> None:
        unregister_large_doc_ingest_callback()

    @pytest.mark.asyncio
    async def test_skips_when_exceeds_max_pages_limit(self) -> None:
        cb = AsyncMock()
        register_large_doc_ingest_callback(cb)
        result = FakePDFResult(text="hello", page_count=RAG_MAX_PAGES_LIMIT + 1)
        await _schedule_rag_ingest("/tmp/huge.pdf", b"data", result, FakeConfig, AsyncMock())
        cb.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_boundary_exactly_max_pages_limit_is_accepted(self) -> None:
        """page_count == RAG_MAX_PAGES_LIMIT should be accepted (not >)."""
        cb = AsyncMock()
        register_large_doc_ingest_callback(cb)
        result = FakePDFResult(text="text", page_count=RAG_MAX_PAGES_LIMIT)
        await _schedule_rag_ingest("/tmp/boundary.pdf", b"data", result, FakeConfig, AsyncMock())
        cb.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_ingests_when_below_default_max(self) -> None:
        cb = AsyncMock()
        register_large_doc_ingest_callback(cb)
        raw_bytes = b"fake pdf"
        result = FakePDFResult(text="hello world", page_count=15)
        await _schedule_rag_ingest("/tmp/small.pdf", raw_bytes, result, FakeConfig, AsyncMock())
        expected_hash = hashlib.sha256(raw_bytes[:8192]).hexdigest()[:16]
        cb.assert_awaited_once_with("small.pdf", "hello world", expected_hash)

    @pytest.mark.asyncio
    async def test_reextracts_when_the_first_pass_was_partial(self) -> None:
        """Moderate documents are the hard case: 21-500 pages deliver only the first pass."""
        cb = AsyncMock()
        register_large_doc_ingest_callback(cb)
        raw_bytes = b"fake pdf bytes"
        result = FakePDFResult(text="truncated", page_count=50, parsed_pages=20)
        full_result = FakePDFResult(text="full content all 50 pages", page_count=50)
        mock_extract = AsyncMock(return_value=full_result)

        with (
            patch(
                "myrm_agent_harness.agent.meta_tools.file_ops.utils.pdf_reader._write_to_temp",
                new_callable=AsyncMock,
                return_value="/tmp/fake.pdf",
            ),
            patch("os.unlink"),
        ):
            await _schedule_rag_ingest("/tmp/large.pdf", raw_bytes, result, FakeConfig, mock_extract)

        expected_hash = hashlib.sha256(raw_bytes[:8192]).hexdigest()[:16]
        cb.assert_awaited_once_with("large.pdf", "full content all 50 pages", expected_hash)
        # The re-read feeds the wiki, never the prompt: rendering its page images would be wasted work.
        reextract_config = mock_extract.await_args.args[1]
        assert reextract_config.max_pages == RAG_MAX_PAGES_LIMIT
        assert reextract_config.extract_embedded_images is False

    @pytest.mark.asyncio
    async def test_no_reextraction_when_every_page_was_delivered(self) -> None:
        cb = AsyncMock()
        register_large_doc_ingest_callback(cb)
        result = FakePDFResult(text="whole document", page_count=600, parsed_pages=600)
        mock_extract = AsyncMock()

        await _schedule_rag_ingest("/tmp/full.pdf", b"data", result, FakeConfig, mock_extract)

        mock_extract.assert_not_awaited()
        cb.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_skips_ingest_when_no_text_was_delivered(self) -> None:
        """A scan without an OCR layer has no text to index; an empty entry would only cost a compile."""
        cb = AsyncMock()
        register_large_doc_ingest_callback(cb)
        result = FakePDFResult(text="", page_count=40, parsed_pages=30)
        full_result = FakePDFResult(text="   ", page_count=40)
        mock_extract = AsyncMock(return_value=full_result)

        with (
            patch(
                "myrm_agent_harness.agent.meta_tools.file_ops.utils.pdf_reader._write_to_temp",
                new_callable=AsyncMock,
                return_value="/tmp/fake.pdf",
            ),
            patch("os.unlink"),
        ):
            await _schedule_rag_ingest("/tmp/scan.pdf", b"data", result, FakeConfig, mock_extract)

        cb.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_reextraction_failure_falls_back_to_delivered_text(self) -> None:
        """When re-extraction fails, should use the text the first pass delivered."""
        cb = AsyncMock()
        register_large_doc_ingest_callback(cb)
        raw_bytes = b"pdf data"
        result = FakePDFResult(text="original truncated", page_count=50, parsed_pages=20)
        mock_extract = AsyncMock(side_effect=RuntimeError("extraction boom"))

        with (
            patch(
                "myrm_agent_harness.agent.meta_tools.file_ops.utils.pdf_reader._write_to_temp",
                new_callable=AsyncMock,
                return_value="/tmp/fake.pdf",
            ),
            patch("os.unlink"),
        ):
            await _schedule_rag_ingest("/tmp/fail.pdf", raw_bytes, result, FakeConfig, mock_extract)

        expected_hash = hashlib.sha256(raw_bytes[:8192]).hexdigest()[:16]
        cb.assert_awaited_once_with("fail.pdf", "original truncated", expected_hash)

    @pytest.mark.asyncio
    async def test_exception_caught_in_outer_try(self) -> None:
        cb = AsyncMock()
        register_large_doc_ingest_callback(cb)

        class BadCoverageResult:
            text = "text"
            page_count = 25

            @property
            def parsed_pages(self) -> int:
                raise RuntimeError("coverage broke")

        await _schedule_rag_ingest("/tmp/bad.pdf", b"data", BadCoverageResult(), FakeConfig, AsyncMock())

        cb.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_sha256_hash_deterministic(self) -> None:
        """Verify that doc_hash is SHA256 of first 8KB, truncated to 16 chars."""
        cb = AsyncMock()
        register_large_doc_ingest_callback(cb)
        raw_bytes = b"A" * 16384
        result = FakePDFResult(text="text", page_count=10)
        await _schedule_rag_ingest("/tmp/hash.pdf", raw_bytes, result, FakeConfig, AsyncMock())
        expected = hashlib.sha256(raw_bytes[:8192]).hexdigest()[:16]
        actual_hash = cb.call_args[0][2]
        assert actual_hash == expected
        assert len(actual_hash) == 16

    @pytest.mark.asyncio
    async def test_temp_file_cleaned_up_even_on_extract_failure(self) -> None:
        """os.unlink must be called in finally block even when extraction fails."""
        cb = AsyncMock()
        register_large_doc_ingest_callback(cb)
        result = FakePDFResult(text="text", page_count=50, parsed_pages=20)
        mock_extract = AsyncMock(side_effect=RuntimeError("boom"))

        with (
            patch(
                "myrm_agent_harness.agent.meta_tools.file_ops.utils.pdf_reader._write_to_temp",
                new_callable=AsyncMock,
                return_value="/tmp/cleanup.pdf",
            ),
            patch("os.unlink") as mock_unlink,
        ):
            await _schedule_rag_ingest("/tmp/t.pdf", b"data", result, FakeConfig, mock_extract)

        mock_unlink.assert_called_once_with("/tmp/cleanup.pdf")


class TestReadPdfRagHint:
    def setup_method(self) -> None:
        unregister_large_doc_ingest_callback()

    def teardown_method(self) -> None:
        unregister_large_doc_ingest_callback()

    @pytest.mark.asyncio
    async def test_small_doc_no_rag_hint(self) -> None:
        """Documents <= RAG_PAGE_THRESHOLD should not have RAG hint."""
        executor = AsyncMock()
        executor.read_file_bytes = AsyncMock(return_value=b"bytes")
        small_result = FakePDFResult(text="Hello world", page_count=RAG_PAGE_THRESHOLD)
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
                return_value=small_result,
            ),
            patch(
                "myrm_agent_harness.toolkits.file_parsers.pdf.pdf_content_extractor.PDFExtractConfig",
                FakeConfig,
            ),
        ):
            result = await read_pdf_as_content_blocks("/tmp/s.pdf", executor, False)
        assert "RAG Auto-Index" not in result
        assert "Hello world" in result

    @pytest.mark.asyncio
    async def test_large_doc_rag_hint_with_callback(self) -> None:
        """Documents > RAG_PAGE_THRESHOLD with callback should have RAG hint."""
        cb = AsyncMock()
        register_large_doc_ingest_callback(cb)
        executor = AsyncMock()
        executor.read_file_bytes = AsyncMock(return_value=b"bytes")
        large_result = FakePDFResult(text="Content", page_count=RAG_PAGE_THRESHOLD + 1, parsed_pages=RAG_PAGE_THRESHOLD)
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
                return_value=large_result,
            ),
            patch(
                "myrm_agent_harness.toolkits.file_parsers.pdf.pdf_content_extractor.PDFExtractConfig",
                FakeConfig,
            ),
        ):
            result = await read_pdf_as_content_blocks("/tmp/l.pdf", executor, False)
        assert "RAG Auto-Index" in result
        assert "wiki_query" in result
        await asyncio.sleep(0.1)

    @pytest.mark.asyncio
    async def test_beyond_ingest_limit_reports_partial_read_without_index_claim(self) -> None:
        """Past RAG_MAX_PAGES_LIMIT nothing is indexed, so the hint must not claim it was."""
        cb = AsyncMock()
        register_large_doc_ingest_callback(cb)
        executor = AsyncMock()
        executor.read_file_bytes = AsyncMock(return_value=b"bytes")
        huge_result = FakePDFResult(
            text="Content",
            page_count=RAG_MAX_PAGES_LIMIT + 500,
            parsed_pages=RAG_PAGE_THRESHOLD,
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
                return_value=huge_result,
            ),
            patch(
                "myrm_agent_harness.toolkits.file_parsers.pdf.pdf_content_extractor.PDFExtractConfig",
                FakeConfig,
            ),
        ):
            result = await read_pdf_as_content_blocks("/tmp/huge.pdf", executor, False)

        assert "Partial Read" in result
        assert "RAG Auto-Index" not in result
        assert "auto-indexed" not in result
        assert f"{RAG_MAX_PAGES_LIMIT}-page auto-index limit" in result
        await asyncio.sleep(0.1)
        cb.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_large_doc_no_rag_without_callback(self) -> None:
        """Large doc without registered callback should NOT have RAG hint."""
        executor = AsyncMock()
        executor.read_file_bytes = AsyncMock(return_value=b"bytes")
        large_result = FakePDFResult(text="Content", page_count=RAG_PAGE_THRESHOLD + 1)
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
                return_value=large_result,
            ),
            patch(
                "myrm_agent_harness.toolkits.file_parsers.pdf.pdf_content_extractor.PDFExtractConfig",
                FakeConfig,
            ),
        ):
            result = await read_pdf_as_content_blocks("/tmp/no_cb.pdf", executor, False)
        assert "RAG Auto-Index" not in result

    @pytest.mark.asyncio
    async def test_rag_hint_does_not_promise_searchable_scanned_pages(self) -> None:
        """Scanned pages are indexed as empty, so "search any page" would be a false promise.

        The 20-page read window also never inspects pages past it, so the caveat cannot be
        derived from what this pass happened to see.
        """
        executor = AsyncMock()
        executor.read_file_bytes = AsyncMock(return_value=b"bytes")
        large = FakePDFResult(text="body " * 100, page_count=40, parsed_pages=20)

        async def _ingest(filename: str, full_text: str, doc_hash: str) -> None:
            return None

        register_large_doc_ingest_callback(_ingest)
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
        assert "[RAG Auto-Index]" in result
        assert "search any page" not in result
        assert "pages that are scanned images carry no searchable text" in result


# ---------------------------------------------------------------------------
# Non-blocking create_task timing verification
# ---------------------------------------------------------------------------


class TestNonBlockingCreateTask:
    @pytest.mark.asyncio
    async def test_create_task_used_not_await(self) -> None:
        events: list[str] = []

        async def slow_ingest(filename: str, full_text: str, doc_hash: str) -> None:
            await asyncio.sleep(0.1)
            events.append("ingest_done")

        register_large_doc_ingest_callback(slow_ingest)
        result = FakePDFResult(text="text", page_count=5)
        task = asyncio.create_task(_schedule_rag_ingest("/tmp/test.pdf", b"bytes", result, FakeConfig, AsyncMock()))
        events.append("main_returned")

        assert events == ["main_returned"]
        await asyncio.sleep(0.2)
        await task
        assert "ingest_done" in events
        unregister_large_doc_ingest_callback()

    @pytest.mark.asyncio
    async def test_full_pipeline_real_pdf_physical_slicing_integration(self, tmp_path) -> None:
        """Integration test with real PDF pipeline: physical slicing limits parsed pages without false string split."""
        from myrm_agent_harness.toolkits.file_parsers.base import PDFParseResult

        executor = AsyncMock()
        executor.read_file_bytes = AsyncMock(return_value=b"dummy_bytes")

        ingest_called = []

        async def mock_ingest(filename: str, full_text: str, doc_hash: str) -> None:
            ingest_called.append((filename, doc_hash))

        register_large_doc_ingest_callback(mock_ingest)
        try:
            fake_extract_result = PDFParseResult(
                text="[Page 1]\nReal content line 1\n\n[Page 2]\nReal content line 2",
                tables=[],
                metadata={"page_count": 25, "parsed_pages": 20},
            )
            # Use real PDFExtractResult structure
            from myrm_agent_harness.toolkits.file_parsers.pdf.pdf_content_extractor import PDFExtractResult

            real_result = PDFExtractResult(
                text=fake_extract_result.text,
                page_count=25,
                parsed_pages=20,
                strategy="text",
            )
            with patch(
                "myrm_agent_harness.toolkits.file_parsers.pdf.pdf_content_extractor.extract_pdf_content",
                new_callable=AsyncMock,
                return_value=real_result,
            ):
                result = await read_pdf_as_content_blocks("/tmp/integration_25p.pdf", executor, supports_vision=False)
                assert isinstance(result, str)
                assert "[RAG Auto-Index]" in result
                assert "25 pages" in result
                assert "Only the first 20 pages" in result
                assert "full document (25 pages) has been auto-indexed" in result
                await asyncio.sleep(0.1)
        finally:
            unregister_large_doc_ingest_callback()
