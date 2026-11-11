"""Text responses become documents as they are; only web pages are converted from HTML."""

from __future__ import annotations

import pytest

from myrm_agent_harness.toolkits.web_fetch.fetchers.protocols import FetchResult
from myrm_agent_harness.toolkits.web_fetch.processing.pipeline import ContentPipeline
from myrm_agent_harness.utils.content_sniff import PayloadKind

URL = "https://example.org/notes.txt"


def _text(body: str, *, content_type: str = "text/plain") -> FetchResult:
    return FetchResult(html=body, url=URL, headers={"content-type": content_type}, kind=PayloadKind.TEXT)


@pytest.fixture
def pipeline() -> ContentPipeline:
    return ContentPipeline()


@pytest.mark.parametrize(
    ("body", "content_type"),
    [
        ("# Title\n\n- one <b>kept</b>\n- two\n", "text/markdown"),
        ("name,qty\nwidget,3\n", "text/csv"),
        ("ok", "text/plain"),
        ("<rss><channel><title>Feed</title></channel></rss>", "application/rss+xml"),
    ],
    ids=["markdown", "csv", "short", "feed"],
)
def test_text_keeps_its_line_breaks_and_markup(pipeline: ContentPipeline, body: str, content_type: str) -> None:
    doc = pipeline.process(_text(f"\n{body}\n\n", content_type=content_type))

    assert doc is not None
    assert doc.page_content == body.strip()
    assert doc.metadata["url"] == URL


@pytest.mark.parametrize("body", ["", "   ", "\n\t\n"])
def test_blank_text_has_no_document(pipeline: ContentPipeline, body: str) -> None:
    assert pipeline.process(_text(body)) is None


def test_json_text_keeps_the_fenced_structured_document(pipeline: ContentPipeline) -> None:
    doc = pipeline.process(_text('{"a":1}', content_type="application/json"))

    assert doc is not None
    assert doc.page_content == '```json\n{\n  "a": 1\n}\n```'


def test_web_page_is_still_converted_from_html(pipeline: ContentPipeline) -> None:
    html = (
        "<html><body><article><h1>Heading</h1><p>"
        + "A readable paragraph of text. " * 12
        + "</p></article></body></html>"
    )

    doc = pipeline.process(FetchResult(html=html, url=URL, headers={"content-type": "text/html"}))

    assert doc is not None
    assert "<p>" not in doc.page_content
    assert "Heading" in doc.page_content
