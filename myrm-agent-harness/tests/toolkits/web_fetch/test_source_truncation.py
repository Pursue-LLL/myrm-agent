"""A source the fetcher cut at its size ceiling is flagged on its Document, and the model is told.

``ContentPipeline.process`` sets the flag once for every path that builds a Document; the binary router sets it on a
parsed file whose text it cuts at ``MAX_PARSED_CHARS``. The full-content tool names the cut pages in a notice that sits
outside the untrusted boundary, so a page cannot forge or suppress it.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.documents import Document

from myrm_agent_harness.toolkits.web_fetch import web_fetch_tools
from myrm_agent_harness.toolkits.web_fetch.engine import FetchEngine
from myrm_agent_harness.toolkits.web_fetch.fetchers.protocols import FetchResult
from myrm_agent_harness.toolkits.web_fetch.processing.binary_router import MAX_PARSED_CHARS, route_binary_content
from myrm_agent_harness.toolkits.web_fetch.processing.full_content_delivery import FetchedPage, plan_full_content
from myrm_agent_harness.toolkits.web_fetch.processing.pipeline import SOURCE_TRUNCATED_KEY, ContentPipeline
from myrm_agent_harness.toolkits.web_fetch.web_fetch_agent_tools import _fetch_full_content
from myrm_agent_harness.utils.content_sniff import PayloadKind

URL = "https://example.org/page"
HTML_PAGE = "<html><body><article><p>" + "readable page text " * 20 + "</p></article></body></html>"
NOTICE_LEAD = "Size limit reached for"


@pytest.mark.parametrize("source_truncated", [True, False])
@pytest.mark.parametrize(
    ("html", "content_type", "kind"),
    [
        ('{"status": "ok"}', "application/json", PayloadKind.TEXT),
        ("<rss><channel><title>Feed</title></channel></rss>", "application/xml", PayloadKind.TEXT),
        ("a plain text answer that is long enough to be kept as a document", "text/plain", PayloadKind.TEXT),
        (HTML_PAGE, "text/html", PayloadKind.WEB),
    ],
    ids=["json", "xml", "text", "html"],
)
def test_pipeline_flags_a_cut_source_on_every_path(
    html: str, content_type: str, kind: PayloadKind, source_truncated: bool
) -> None:
    result = FetchResult(
        html=html,
        url=URL,
        headers={"content-type": content_type},
        kind=kind,
        source_truncated=source_truncated,
    )

    document = ContentPipeline().process(result)

    assert document is not None
    assert (SOURCE_TRUNCATED_KEY in document.metadata) is source_truncated


@pytest.mark.asyncio
async def test_cache_hit_returns_the_flagged_document() -> None:
    engine = FetchEngine()
    document = Document(page_content="test", metadata={"url": "https://example.com", SOURCE_TRUNCATED_KEY: True})

    with patch.object(engine, "_crawl_with_degradation", new_callable=AsyncMock) as crawl:
        crawl.return_value = (document, None)
        await engine.crawl("https://example.com")
        cached = await engine.crawl("https://example.com")

    assert crawl.call_count == 1
    assert cached is not None
    assert cached.metadata[SOURCE_TRUNCATED_KEY] is True
    await engine.shutdown()


def _page(body: str = "short body", *, cut: bool = False) -> FetchedPage:
    return FetchedPage(url=URL, title="page", body=body, source_truncated=cut)


def test_notice_names_the_cut_pages_by_their_numbers() -> None:
    delivery = plan_full_content([_page(cut=True), _page(), _page(cut=True)], indices=[4, 5, 9])

    assert NOTICE_LEAD in delivery.source_notice
    assert "【4】【9】" in delivery.source_notice
    assert "【5】" not in delivery.source_notice


def test_no_notice_when_no_source_was_cut() -> None:
    assert plan_full_content([_page(), _page()]).source_notice == ""


def test_notice_stays_out_of_the_page_text_and_survives_the_budget_cut() -> None:
    long_body = "\n".join(f"line {line} " + "x" * 80 for line in range(400))

    delivery = plan_full_content([_page(long_body, cut=True)])

    assert delivery.stored_text is not None
    assert "【1】" in delivery.source_notice
    assert NOTICE_LEAD not in delivery.visible_text


def _page_document(url: str, *, cut: bool) -> Document:
    metadata: dict[str, str | bool] = {"url": url, "title": ""}
    if cut:
        metadata[SOURCE_TRUNCATED_KEY] = True
    return Document(page_content=f"body of {url}", metadata=metadata)


def _serve(monkeypatch: pytest.MonkeyPatch, *, cut: frozenset[str]) -> None:
    """Make the tool's engine return one short page per URL; the URLs in ``cut`` carry the source-cut flag."""

    async def crawl_many(urls: list[str]) -> tuple[list[tuple[str, Document]], list[tuple[str, None]]]:
        return [(url, _page_document(url, cut=url in cut)) for url in urls], []

    monkeypatch.setattr(web_fetch_tools, "crawl_many", crawl_many)


@pytest.mark.asyncio
async def test_tool_puts_the_notice_after_the_untrusted_boundary(monkeypatch: pytest.MonkeyPatch) -> None:
    _serve(monkeypatch, cut=frozenset({"https://b.example/2"}))

    result = await _fetch_full_content(["https://a.example/1", "https://b.example/2"])

    inside, outside = str(result["content"]).split("<<<END_UNTRUSTED_DATA", 1)
    assert NOTICE_LEAD not in inside
    assert f"{NOTICE_LEAD} 【2】:" in outside


@pytest.mark.asyncio
async def test_tool_adds_no_notice_when_every_source_was_read_whole(monkeypatch: pytest.MonkeyPatch) -> None:
    _serve(monkeypatch, cut=frozenset())

    result = await _fetch_full_content(["https://a.example/1"])

    assert NOTICE_LEAD not in str(result["content"])


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("parsed_chars", "notice_expected"),
    [(MAX_PARSED_CHARS + 1, True), (MAX_PARSED_CHARS, False)],
    ids=["text_over_the_cap", "text_at_the_cap"],
)
async def test_tool_names_a_document_whose_parsed_text_the_router_cut(
    monkeypatch: pytest.MonkeyPatch, parsed_chars: int, notice_expected: bool
) -> None:
    parser = AsyncMock()
    parser.parse = AsyncMock(return_value=("report line\n" * parsed_chars)[:parsed_chars])
    with patch("myrm_agent_harness.toolkits.file_parsers.get_parser", return_value=parser):
        document = await route_binary_content(
            b"%PDF-1.4 fake pdf", {"content-type": "application/pdf"}, "https://a.example/report.pdf"
        )
    assert document is not None

    async def crawl_many(urls: list[str]) -> tuple[list[tuple[str, Document]], list[tuple[str, None]]]:
        return [(urls[0], document)], []

    monkeypatch.setattr(web_fetch_tools, "crawl_many", crawl_many)

    result = await _fetch_full_content(["https://a.example/report.pdf"])

    _, outside = str(result["content"]).split("<<<END_UNTRUSTED_DATA", 1)
    assert (f"{NOTICE_LEAD} 【1】:" in outside) is notice_expected
