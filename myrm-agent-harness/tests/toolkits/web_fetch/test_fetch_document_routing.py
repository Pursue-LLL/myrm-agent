"""Payloads fetched over L1 are read as what they are, not mistaken for an empty page.

The HTTP fetcher classifies every body: web pages go through the HTML pipeline, text (plain, markdown, csv,
feeds) is returned as it is, and files (PDF, Office, downloads) arrive as ``raw_body`` with an empty ``html``.
The engine parses a file first; a file no parser accepts ends the fetch, because a browser cannot read it
either. An error status instead means the server refused the request, which a browser tier may get past.
"""

from __future__ import annotations

import io
from collections.abc import AsyncIterator, Callable
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from myrm_agent_harness.toolkits.web_fetch.engine import FetchEngine
from myrm_agent_harness.toolkits.web_fetch.fetchers.protocols import FetcherType, FetchResult
from myrm_agent_harness.toolkits.web_fetch.processing.binary_router import MAX_PARSED_CHARS
from myrm_agent_harness.toolkits.web_fetch.processing.pipeline import SOURCE_TRUNCATED_KEY
from myrm_agent_harness.utils.content_sniff import PayloadKind
from tests.support.minimal_pdf import minimal_pdf_bytes

URL = "http://example.com/file"
MARKER = "DOC-MARKER-4711"
DOCX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
EXE_HEADERS = {"content-type": "application/octet-stream", "content-disposition": 'attachment; filename="setup.exe"'}
EXE_BODY = b"MZ\x90\x00" + bytes(range(256)) * 8


def _docx_bytes(text: str) -> bytes:
    docx = pytest.importorskip("docx")
    buffer = io.BytesIO()
    document = docx.Document()
    document.add_paragraph(text)
    document.save(buffer)
    return buffer.getvalue()


def _text_result(text: str, *, content_type: str = "text/plain", status_code: int = 200) -> FetchResult:
    return FetchResult(
        html=text, url=URL, status_code=status_code, headers={"content-type": content_type}, kind=PayloadKind.TEXT
    )


def _exe_result(*, status_code: int = 200) -> FetchResult:
    return FetchResult(html="", url=URL, status_code=status_code, headers=EXE_HEADERS, raw_body=EXE_BODY)


@pytest.fixture
async def engine_with_http() -> AsyncIterator[tuple[FetchEngine, AsyncMock]]:
    engine = FetchEngine()
    http = AsyncMock()
    engine._http_fetcher = http
    engine._browser_fetcher = AsyncMock()
    engine._browser_fetcher.set_launch_mode_preference = MagicMock()
    engine._stealth_fetcher = AsyncMock()
    yield engine, http
    await engine.shutdown()


@pytest.mark.parametrize(
    ("make_body", "content_type"),
    [(minimal_pdf_bytes, "application/pdf"), (_docx_bytes, DOCX_CONTENT_TYPE)],
    ids=["pdf", "docx"],
)
async def test_document_is_parsed_instead_of_degraded(
    engine_with_http: tuple[FetchEngine, AsyncMock],
    make_body: Callable[[str], bytes],
    content_type: str,
) -> None:
    engine, http = engine_with_http
    http.fetch.return_value = FetchResult(
        html="", url=URL, headers={"content-type": content_type}, raw_body=make_body(MARKER)
    )

    doc, degradable, _ = await engine._try_fetch_and_process(URL, FetcherType.HTTP)

    assert doc is not None
    assert MARKER in doc.page_content
    assert degradable is False


async def test_document_text_over_the_parser_cap_reaches_the_caller_flagged(
    engine_with_http: tuple[FetchEngine, AsyncMock],
) -> None:
    engine, http = engine_with_http
    http.fetch.return_value = FetchResult(
        html="", url=URL, headers={"content-type": "application/pdf"}, raw_body=minimal_pdf_bytes(MARKER)
    )
    parser = AsyncMock()
    parser.parse = AsyncMock(return_value=MARKER + "x" * MAX_PARSED_CHARS)

    with patch("myrm_agent_harness.toolkits.file_parsers.get_parser", return_value=parser):
        doc, degradable, _ = await engine._try_fetch_and_process(URL, FetcherType.HTTP)

    assert doc is not None
    assert degradable is False
    assert doc.page_content.startswith(MARKER)
    assert len(doc.page_content) == MAX_PARSED_CHARS
    assert doc.metadata[SOURCE_TRUNCATED_KEY] is True


async def test_file_no_parser_reads_ends_the_fetch(engine_with_http: tuple[FetchEngine, AsyncMock]) -> None:
    engine, http = engine_with_http
    http.fetch.return_value = _exe_result()

    doc, degradable, _ = await engine._try_fetch_and_process(URL, FetcherType.HTTP)

    assert doc is None
    assert degradable is False


async def test_file_no_parser_reads_behind_an_error_status_still_degrades(
    engine_with_http: tuple[FetchEngine, AsyncMock],
) -> None:
    engine, http = engine_with_http
    http.fetch.return_value = _exe_result(status_code=403)

    doc, degradable, _ = await engine._try_fetch_and_process(URL, FetcherType.HTTP)

    assert doc is None
    assert degradable is True


@pytest.mark.parametrize(
    ("content_type", "text"),
    [
        ("text/markdown", "# Title\n\n- one\n- two <b>kept</b>\n"),
        ("text/csv", "name,qty\nwidget,3\ngadget,5\n"),
        ("application/rss+xml", '<?xml version="1.0"?>\n<rss><channel><title>Feed</title></channel></rss>'),
        ("text/plain", "line one\nline two\n"),
    ],
    ids=["markdown", "csv", "feed", "plain"],
)
async def test_text_is_returned_as_it_is(
    engine_with_http: tuple[FetchEngine, AsyncMock], content_type: str, text: str
) -> None:
    engine, http = engine_with_http
    http.fetch.return_value = _text_result(text, content_type=content_type)

    doc, _, _ = await engine._try_fetch_and_process(URL, FetcherType.HTTP)

    assert doc is not None
    assert doc.page_content == text.strip()
    assert doc.metadata["url"] == URL


@pytest.mark.parametrize("status_code", [403, 429])
async def test_text_behind_an_error_status_still_degrades(
    engine_with_http: tuple[FetchEngine, AsyncMock], status_code: int
) -> None:
    engine, http = engine_with_http
    http.fetch.return_value = _text_result("Forbidden", status_code=status_code)

    doc, degradable, _ = await engine._try_fetch_and_process(URL, FetcherType.HTTP)

    assert doc is None
    assert degradable is True


async def test_empty_text_degrades(engine_with_http: tuple[FetchEngine, AsyncMock]) -> None:
    engine, http = engine_with_http
    http.fetch.return_value = _text_result("  \n")

    doc, degradable, _ = await engine._try_fetch_and_process(URL, FetcherType.HTTP)

    assert doc is None
    assert degradable is True


async def test_crawl_reads_text_without_any_browser_tier(engine_with_http: tuple[FetchEngine, AsyncMock]) -> None:
    engine, http = engine_with_http
    http.fetch.return_value = _text_result("plain answer\n")

    doc, _ = await engine._crawl_with_degradation(URL)

    assert doc is not None
    assert doc.page_content == "plain answer"
    engine._browser_fetcher.fetch.assert_not_called()  # type: ignore[attr-defined]
    engine._stealth_fetcher.fetch.assert_not_called()  # type: ignore[attr-defined]


async def test_crawl_stops_at_an_unreadable_file_but_offers_it_to_remote_providers(
    engine_with_http: tuple[FetchEngine, AsyncMock],
) -> None:
    engine, http = engine_with_http
    http.fetch.return_value = _exe_result()

    with patch.object(engine, "_try_escalation", new=AsyncMock(return_value=(None, None))) as escalation:
        doc, result = await engine._crawl_with_degradation(URL)
        assert doc is None
        assert result is not None
        assert result.kind is PayloadKind.BINARY
        escalation.assert_awaited_once()

        escalation.reset_mock()
        await engine._crawl_with_degradation(URL, allow_escalation=False)
        escalation.assert_not_called()

    engine._browser_fetcher.fetch.assert_not_called()  # type: ignore[attr-defined]
    engine._stealth_fetcher.fetch.assert_not_called()  # type: ignore[attr-defined]


async def test_crawl_returns_what_a_remote_provider_reads_from_an_unreadable_file(
    engine_with_http: tuple[FetchEngine, AsyncMock],
) -> None:
    engine, http = engine_with_http
    http.fetch.return_value = _exe_result()
    remote = MagicMock(page_content="read remotely")
    remote_result = FetchResult(html="read remotely", url=URL)

    with patch.object(engine, "_try_escalation", new=AsyncMock(return_value=(remote, remote_result))):
        doc, result = await engine._crawl_with_degradation(URL)

    assert doc is remote
    assert result is remote_result


@pytest.mark.parametrize(
    ("fetched", "reported_success"),
    [
        (FetchResult(html="<html><body>missing</body></html>", url=URL, status_code=404), None),
        (FetchResult(html="", url=URL, status_code=304), None),
        (_exe_result(), None),
        (_text_result("readable\n"), True),
        (_text_result(""), False),
    ],
    ids=["404", "304", "unreadable-file", "text", "empty-text"],
)
async def test_tier_outcomes_come_only_from_real_attempts(
    engine_with_http: tuple[FetchEngine, AsyncMock], fetched: FetchResult, reported_success: bool | None
) -> None:
    engine, http = engine_with_http
    http.fetch.return_value = fetched

    with (
        patch.object(engine._tier_breaker, "report") as report,
        patch.object(engine._domain_metrics, "record_failure") as record_failure,
    ):
        await engine._try_and_report(URL, FetcherType.HTTP)

    if reported_success is None:
        report.assert_not_called()
        record_failure.assert_not_called()
    else:
        report.assert_called_once_with("example.com", FetcherType.HTTP, success=reported_success)
        assert record_failure.called is (not reported_success)
