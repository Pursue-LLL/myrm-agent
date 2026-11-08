"""Tests for the numbers format_documents_with_metadata puts in front of each source.

Without an indexer a result numbers its sources from 1. A run hands the formatter an indexer (the run's
``SourceTracker.index_for``), so every number a tool prints is the index of the card the stream issues for it.
"""

from __future__ import annotations

import re
from collections.abc import Mapping

from langchain_core.documents import Document

from myrm_agent_harness.utils.context_format import format_documents_with_metadata


def _docs(*urls: str) -> list[Document]:
    return [
        Document(
            page_content=f"body of {url}",
            metadata={"url": url, "title": f"Title {n}", "snippet": f"Snippet {n}", "date": ""},
        )
        for n, url in enumerate(urls)
    ]


def _labels(text: str) -> list[tuple[int, str]]:
    return [(int(match.group(1)), match.group(2)) for match in re.finditer(r"【(\d+)】 URL: (\S+)", text)]


def test_a_result_without_an_indexer_numbers_its_sources_from_one() -> None:
    _, text, _ = format_documents_with_metadata(_docs("https://a.com", "https://b.com"))
    assert _labels(text) == [(1, "https://a.com"), (2, "https://b.com")]


def test_the_printed_numbers_are_the_ones_the_indexer_gives() -> None:
    numbers = {"https://a.com": 7, "https://b.com": 3}
    _, text, _ = format_documents_with_metadata(_docs(*numbers), index_for=lambda source: numbers[str(source["url"])])
    assert _labels(text) == [(7, "https://a.com"), (3, "https://b.com")]


def test_the_indexer_is_asked_with_the_entry_that_becomes_the_source() -> None:
    asked: list[dict[str, object]] = []

    def index_for(source: Mapping[str, object]) -> int:
        asked.append(dict(source))
        return len(asked)

    sources, _, _ = format_documents_with_metadata(_docs("https://a.com", "https://b.com"), index_for=index_for)
    assert asked == sources


def test_chunks_of_one_page_share_one_number_and_ask_once() -> None:
    asked: list[str] = []

    def index_for(source: Mapping[str, object]) -> int:
        asked.append(str(source["url"]))
        return 10 + len(asked)

    sources, text, _ = format_documents_with_metadata(
        _docs("https://a.com", "https://a.com", "https://b.com"), index_for=index_for
    )
    assert asked == ["https://a.com", "https://b.com"]
    assert len(sources) == 2
    assert _labels(text) == [(11, "https://a.com"), (12, "https://b.com")]


def test_a_budget_that_drops_documents_keeps_the_numbers_of_the_ones_kept() -> None:
    urls = [f"https://site{n}.example/page" for n in range(8)]
    sources, text, _ = format_documents_with_metadata(
        _docs(*urls),
        total_max_tokens=150,
        index_for=lambda source: 40 + urls.index(str(source["url"])),
    )
    kept = _labels(text)
    assert 0 < len(kept) < len(urls)
    assert kept == [(40 + n, urls[n]) for n in range(len(kept))]
    assert [source["url"] for source in sources] == [url for _, url in kept]
