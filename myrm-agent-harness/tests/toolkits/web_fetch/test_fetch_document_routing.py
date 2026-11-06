"""Documents fetched over L1 are parsed, not mistaken for an empty page and sent to the browser.

The HTTP fetcher hands a non-text body (PDF, Office, downloads) to the engine as ``raw_body``
with an empty ``html``. The engine must try the file parsers first; only a payload no parser
accepts degrades to the browser tier.
"""

from __future__ import annotations

import io
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from myrm_agent_harness.toolkits.web_fetch.engine import FetchEngine
from myrm_agent_harness.toolkits.web_fetch.fetchers.protocols import FetcherType, FetchResult

URL = "http://example.com/file"
MARKER = "DOC-MARKER-4711"
DOCX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _pdf_bytes(text: str) -> bytes:
    """A one-page PDF with a real text layer, small enough to build by hand."""
    stream = f"BT /F1 18 Tf 72 720 Td ({text}) Tj ET".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    body = b"%PDF-1.4\n"
    offsets: list[int] = []
    for number, obj in enumerate(objects, start=1):
        offsets.append(len(body))
        body += b"%d 0 obj\n%s\nendobj\n" % (number, obj)
    xref_offset = len(body)
    body += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    body += b"".join(b"%010d 00000 n \n" % offset for offset in offsets)
    body += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref_offset)
    return body


def _docx_bytes(text: str) -> bytes:
    docx = pytest.importorskip("docx")
    buffer = io.BytesIO()
    document = docx.Document()
    document.add_paragraph(text)
    document.save(buffer)
    return buffer.getvalue()


@pytest.fixture
async def engine_with_http(tmp_path: Path) -> AsyncIterator[tuple[FetchEngine, AsyncMock]]:
    engine = FetchEngine(adaptive_router_rules_file=tmp_path / "rules.pkl")
    http = AsyncMock()
    engine._http_fetcher = http  # type: ignore[assignment]
    yield engine, http
    await engine.shutdown()


@pytest.mark.parametrize(
    ("make_body", "content_type"),
    [(_pdf_bytes, "application/pdf"), (_docx_bytes, DOCX_CONTENT_TYPE)],
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

    doc, degradable, *_ = await engine._try_fetch_and_process(URL, FetcherType.HTTP)

    assert doc is not None
    assert MARKER in doc.page_content
    assert degradable is False


@pytest.mark.parametrize("content_type", ["application/xhtml+xml", "application/ld+json", "application/octet-stream"])
async def test_non_text_page_no_parser_accepts_still_degrades_to_the_browser(
    engine_with_http: tuple[FetchEngine, AsyncMock], content_type: str
) -> None:
    engine, http = engine_with_http
    http.fetch.return_value = FetchResult(
        html="", url=URL, headers={"content-type": content_type}, raw_body=b"<html><body>page</body></html>"
    )

    doc, degradable, *_ = await engine._try_fetch_and_process(URL, FetcherType.HTTP)

    assert doc is None
    assert degradable is True


async def test_binary_download_without_a_parser_degrades_instead_of_reaching_the_model(
    engine_with_http: tuple[FetchEngine, AsyncMock],
) -> None:
    engine, http = engine_with_http
    headers = {"content-type": "application/octet-stream", "content-disposition": 'attachment; filename="setup.exe"'}
    http.fetch.return_value = FetchResult(
        html="", url=URL, headers=headers, raw_body=b"MZ\x90\x00" + bytes(range(256)) * 8
    )

    doc, degradable, *_ = await engine._try_fetch_and_process(URL, FetcherType.HTTP)

    assert doc is None
    assert degradable is True
