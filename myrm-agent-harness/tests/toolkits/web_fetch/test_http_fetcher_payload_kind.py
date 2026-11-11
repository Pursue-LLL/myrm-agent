"""L1 classifies each response body once: web page, text or binary file.

A web page keeps the HTML pipeline, text is decoded and kept as it is, and a file travels as ``raw_body`` so the
file parsers get its exact bytes. The HTTP/3 retry lane only helps web pages that came back empty or blocked.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from myrm_agent_harness.toolkits.web_fetch.fetchers.http_fetcher import (
    MAX_HTML_BODY_BYTES,
    MAX_PLAIN_TEXT_BODY_BYTES,
    HttpFetcher,
)
from myrm_agent_harness.toolkits.web_fetch.fetchers.protocols import FetchResult
from myrm_agent_harness.utils.content_sniff import PayloadKind

URL = "https://example.org/resource"
HTML_PAGE = b"<!DOCTYPE html><html><body><article><p>" + b"readable page text " * 20 + b"</p></article></body></html>"
PDF = b"%PDF-1.7\n1 0 obj\n<< /Type /Catalog >>\nendobj\n" + b"\x00" * 64


def _convert(body: bytes, content_type: str | None, *, status: int = 200, encoding: str | None = None) -> FetchResult:
    headers = {"content-type": content_type} if content_type else {}
    response = SimpleNamespace(status=status, headers=headers, body=body, url=URL, encoding=encoding)
    return HttpFetcher._response_to_fetch_result(response, URL)


@pytest.mark.parametrize(
    ("body", "content_type", "kind"),
    [
        (HTML_PAGE, "text/html; charset=utf-8", PayloadKind.WEB),
        (HTML_PAGE, None, PayloadKind.WEB),
        (HTML_PAGE, "application/octet-stream", PayloadKind.WEB),
        (b"# Notes\n\n- one\n- two\n", "text/markdown", PayloadKind.TEXT),
        (b"name,qty\nwidget,3\n", "application/octet-stream", PayloadKind.TEXT),
        (b'{"@context": "https://schema.org"}', "application/ld+json", PayloadKind.TEXT),
        (b"<rss><channel><title>Feed</title></channel></rss>", "application/rss+xml", PayloadKind.TEXT),
        (b"plain answer", None, PayloadKind.TEXT),
    ],
    ids=[
        "html",
        "html-untyped",
        "html-octet-stream",
        "markdown",
        "csv-octet-stream",
        "json-ld",
        "rss",
        "plain-untyped",
    ],
)
def test_readable_response_is_decoded_and_keeps_its_kind(
    body: bytes, content_type: str | None, kind: PayloadKind
) -> None:
    result = _convert(body, content_type)

    assert result.kind is kind
    assert result.raw_body is None
    assert result.html == body.decode()


@pytest.mark.parametrize(
    "content_type", ["application/pdf", "text/html", "text/plain", None, "application/octet-stream"]
)
def test_file_travels_as_raw_bytes_whatever_the_server_declared(content_type: str | None) -> None:
    result = _convert(PDF, content_type)

    assert result.kind is PayloadKind.BINARY
    assert result.raw_body == PDF
    assert result.html == ""


def test_text_in_a_declared_charset_is_decoded_with_it() -> None:
    text = "你好，世界。这是一段用国标编码保存的文字。"
    result = _convert(text.encode("gb18030"), "text/plain; charset=gb18030", encoding="gb18030")

    assert result.kind is PayloadKind.TEXT
    assert result.html == text


def test_web_page_above_its_ceiling_is_cut_and_flagged() -> None:
    page = b"<html><body><p>" + b"a" * MAX_HTML_BODY_BYTES + b"</p></body></html>"
    result = _convert(page, "text/html")

    assert result.kind is PayloadKind.WEB
    assert len(result.html) == MAX_HTML_BODY_BYTES
    assert result.source_truncated is True


def test_text_has_a_higher_ceiling_than_a_web_page() -> None:
    whole = _convert(b"a" * (MAX_HTML_BODY_BYTES + 1_000), "text/plain")
    assert whole.kind is PayloadKind.TEXT
    assert len(whole.html) == MAX_HTML_BODY_BYTES + 1_000
    assert whole.source_truncated is False

    cut = _convert(b"a" * (MAX_PLAIN_TEXT_BODY_BYTES + 1_000), "text/plain")
    assert len(cut.html) == MAX_PLAIN_TEXT_BODY_BYTES
    assert cut.source_truncated is True


@pytest.mark.parametrize(
    ("body", "content_type", "ceiling"),
    [
        (b"a" * MAX_HTML_BODY_BYTES, "text/html", MAX_HTML_BODY_BYTES),
        (b"a" * MAX_PLAIN_TEXT_BODY_BYTES, "text/plain", MAX_PLAIN_TEXT_BODY_BYTES),
    ],
    ids=["web-page", "text"],
)
def test_body_exactly_at_its_ceiling_is_not_cut(body: bytes, content_type: str, ceiling: int) -> None:
    result = _convert(body, content_type)

    assert len(result.html) == ceiling
    assert result.source_truncated is False


def test_a_file_is_kept_whole_and_never_flagged() -> None:
    big_file = PDF + b"\x00" * (MAX_PLAIN_TEXT_BODY_BYTES + 1_000)
    result = _convert(big_file, "application/pdf")

    assert result.raw_body == big_file
    assert result.source_truncated is False


def test_cut_inside_a_multibyte_character_decodes_the_whole_characters() -> None:
    # The odd-length prefix puts the ceiling after the first byte of a two-byte character; the half character must
    # be dropped, not turn the page into another charset's reading of its bytes.
    page = b"<p>" + "é".encode() * MAX_HTML_BODY_BYTES
    result = _convert(page, "text/html")

    assert result.source_truncated is True
    assert result.html == "<p>" + "é" * ((MAX_HTML_BODY_BYTES - 3) // 2)


def test_not_modified_response_stays_an_empty_web_result() -> None:
    result = _convert(b"", "text/html", status=304)

    assert result.status_code == 304
    assert result.kind is PayloadKind.WEB
    assert result.raw_body is None


def test_result_carrying_raw_bytes_is_always_binary() -> None:
    assert FetchResult(html="", url=URL, raw_body=b"bytes").kind is PayloadKind.BINARY
    assert FetchResult(html="", url=URL, kind=PayloadKind.TEXT, raw_body=b"bytes").kind is PayloadKind.BINARY
    assert FetchResult(html="<p>page</p>", url=URL).kind is PayloadKind.WEB


@pytest.mark.parametrize(
    ("result", "expected"),
    [
        (FetchResult(html="short", url=URL), True),
        (FetchResult(html="short", url=URL, kind=PayloadKind.TEXT), False),
        (FetchResult(html="", url=URL, raw_body=PDF), False),
        (FetchResult(html="short", url=URL, status_code=403, kind=PayloadKind.TEXT), True),
        (FetchResult(html="short", url=URL, status_code=404), False),
        (None, True),
    ],
    ids=["empty-page", "text", "file", "text-forbidden", "not-found", "no-response"],
)
def test_http3_retry_only_helps_web_pages(result: FetchResult | None, expected: bool) -> None:
    assert HttpFetcher._should_retry_with_http3(result) is expected
