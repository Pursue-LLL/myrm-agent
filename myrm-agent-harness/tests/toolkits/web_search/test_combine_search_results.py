"""Tests for combine_search_results_unified.

Covers: the unified dedup merge (URL key, content hash), the URL a document shows, failed queries, zero-result
queries and SearchAPIError.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from langchain_core.documents import Document

from myrm_agent_harness.toolkits.web_search.core.exceptions import SearchAPIError
from myrm_agent_harness.toolkits.web_search.processing.search_results_processor import combine_search_results_unified


def _search_doc(url: str, title: str = "T", content: str = "snippet") -> Document:
    return Document(
        page_content=content,
        metadata={"url": url, "title": title, "description": content},
    )


_MODULE = "myrm_agent_harness.toolkits.web_search.processing.search_results_processor"


class TestCombineSearchResultsUnified:
    """Tests for combine_search_results_unified."""

    def test_empty_input(self) -> None:
        urls, docs = combine_search_results_unified([])
        assert urls == []
        assert docs == []

    def test_all_queries_failed_raises(self) -> None:
        data: list[tuple[str, list[Document], Exception | None]] = [("q1", [], RuntimeError("network error"))]
        with pytest.raises(SearchAPIError):
            combine_search_results_unified(data)

    def test_all_queries_zero_results_raises(self) -> None:
        data: list[tuple[str, list[Document], Exception | None]] = [("q1", [], None), ("q2", [], None)]
        with pytest.raises(SearchAPIError):
            combine_search_results_unified(data)

    def test_single_query_single_doc(self) -> None:
        doc = _search_doc("https://example.com/page1")
        data = [("q1", [doc], None)]
        urls, docs = combine_search_results_unified(data)
        assert len(docs) == 1
        assert len(urls) == 1
        assert "example.com" in urls[0]["url"]

    def test_dedup_same_url_same_content(self) -> None:
        doc1 = _search_doc("https://example.com/page1", content="same content")
        doc2 = _search_doc("https://example.com/page1", content="same content")
        data = [("q1", [doc1], None), ("q2", [doc2], None)]
        _urls, docs = combine_search_results_unified(data)
        assert len(docs) == 1

    def test_dedup_same_url_different_content_keeps_longest(self) -> None:
        """Same URL with different content: URL arbitration keeps the longest."""
        doc1 = _search_doc("https://example.com/page1", content="short")
        doc2 = _search_doc("https://example.com/page1", content="much longer content here")
        data = [("q1", [doc1], None), ("q2", [doc2], None)]
        _urls, docs = combine_search_results_unified(data)
        assert len(docs) == 1
        assert "much longer" in docs[0].page_content

    def test_different_urls_different_content_both_kept(self) -> None:
        """Different URLs with different content are both kept."""
        doc1 = _search_doc("https://a.com/page1", content="unique content A")
        doc2 = _search_doc("https://b.com/page2", content="unique content B")
        data = [("q1", [doc1, doc2], None)]
        urls, docs = combine_search_results_unified(data)
        assert len(docs) == 2
        assert len(urls) == 2

    def test_different_urls_same_content_mirror_dedup(self) -> None:
        """Different URLs with identical content (mirror sites) are deduplicated."""
        doc1 = _search_doc("https://a.com/page1", content="same content")
        doc2 = _search_doc("https://b.com/page2", content="same content")
        data = [("q1", [doc1, doc2], None)]
        _urls, docs = combine_search_results_unified(data)
        assert len(docs) == 1

    def test_mixed_success_and_failure(self) -> None:
        doc = _search_doc("https://ok.com/page")
        data = [
            ("q1", [doc], None),
            ("q2", [], RuntimeError("fail")),
        ]
        _urls, docs = combine_search_results_unified(data)
        assert len(docs) == 1

    def test_doc_missing_url_skipped(self) -> None:
        doc_ok = _search_doc("https://valid.com/page")
        doc_no_url = Document(
            page_content="no url doc",
            metadata={"title": "T", "description": "d"},
        )
        data = [("q1", [doc_ok, doc_no_url], None)]
        _urls, docs = combine_search_results_unified(data)
        assert len(docs) == 1

    def test_shown_url_is_the_providers_own_url(self) -> None:
        """Case, www and fragment stay as the provider returned them; only the dedup key folds them."""
        url = "https://www.Example.COM/Page#Fragment"
        urls, docs = combine_search_results_unified([("q1", [_search_doc(url)], None)])
        assert [d.metadata["url"] for d in docs] == [url]
        assert [u["url"] for u in urls] == [url]

    def test_shown_url_decodes_non_ascii_escapes(self) -> None:
        _urls, docs = combine_search_results_unified(
            [("q1", [_search_doc("https://zh.wikipedia.org/wiki/%E8%8B%B1%E9%9B%84")], None)]
        )
        assert docs[0].metadata["url"] == "https://zh.wikipedia.org/wiki/英雄"

    @pytest.mark.parametrize("winner_first", [True, False])
    @pytest.mark.parametrize(
        ("winner_url", "loser_url"),
        [
            ("https://example.com/path", "https://www.Example.com/Path/"),
            ("https://www.Example.com/Path/", "https://example.com/path"),
            ("https://example.com/", "https://example.com"),
            ("https://example.com", "https://example.com/"),
        ],
    )
    def test_spelling_variants_collapse_to_the_winners_own_url(
        self, winner_url: str, loser_url: str, winner_first: bool
    ) -> None:
        """Variants share one dedup key; the document with the most content wins and shows its own spelling."""
        winner = _search_doc(winner_url, content="much longer content here")
        loser = _search_doc(loser_url, content="short")
        data = [("q1", [winner, loser] if winner_first else [loser, winner], None)]
        _urls, docs = combine_search_results_unified(data)
        assert [d.metadata["url"] for d in docs] == [winner_url]

    def test_multiple_queries_merge(self) -> None:
        doc1 = _search_doc("https://a.com/1", content="content for a.com")
        doc2 = _search_doc("https://b.com/2", content="content for b.com")
        doc3 = _search_doc("https://c.com/3", content="content for c.com")
        data = [
            ("q1", [doc1, doc2], None),
            ("q2", [doc3], None),
        ]
        urls, docs = combine_search_results_unified(data)
        assert len(docs) == 3
        assert len(urls) == 3

    def test_metadata_preserved(self) -> None:
        doc = _search_doc("https://example.com/page", title="My Title")
        data = [("q1", [doc], None)]
        urls, docs = combine_search_results_unified(data)
        assert docs[0].metadata["title"] == "My Title"
        assert urls[0]["title"] == "My Title"

    def test_a_url_that_is_not_absolute_is_kept_as_it_is(self) -> None:
        """A URL that cannot be read as host and path is its own key: the document stays, its link unchanged."""
        doc = _search_doc("not-a-valid-url-at-all")
        _urls, docs = combine_search_results_unified([("q1", [doc], None)])
        assert [d.metadata["url"] for d in docs] == ["not-a-valid-url-at-all"]

    def test_long_content_truncation_hash(self) -> None:
        """Content >500 chars should use first 500 chars for hash dedup."""
        long_content = "A" * 600
        doc1 = _search_doc("https://a.com/page", content=long_content)
        doc2 = _search_doc("https://a.com/page", content=long_content)
        data = [("q1", [doc1], None), ("q2", [doc2], None)]
        _urls, docs = combine_search_results_unified(data)
        assert len(docs) == 1

    def test_long_content_different_suffix_dedup(self) -> None:
        """Docs with same first 500 chars but different tails should dedup (same hash)."""
        base = "X" * 500
        doc1 = _search_doc("https://a.com/page", content=base + "AAAA")
        doc2 = _search_doc("https://a.com/page", content=base + "BBBB")
        data = [("q1", [doc1], None), ("q2", [doc2], None)]
        _urls, docs = combine_search_results_unified(data)
        assert len(docs) == 1

    def test_search_api_error_context_metadata(self) -> None:
        """SearchAPIError should include query statistics in context."""
        data: list[tuple[str, list[Document], Exception | None]] = [("q1", [], None), ("q2", [], RuntimeError("fail"))]
        with pytest.raises(SearchAPIError) as exc_info:
            combine_search_results_unified(data)
        ctx = exc_info.value.context
        assert ctx is not None
        assert ctx.metadata["total_queries"] == "2"
        assert ctx.metadata["failed_queries"] == "1"

    def test_mixed_failed_zero_success(self) -> None:
        """Mix of failed, zero-result, and successful queries."""
        doc = _search_doc("https://ok.com/page")
        data = [
            ("q1", [doc], None),
            ("q2", [], None),
            ("q3", [], RuntimeError("timeout")),
        ]
        _urls, docs = combine_search_results_unified(data)
        assert len(docs) == 1

    def test_all_docs_skipped_but_total_nonzero(self) -> None:
        """All docs have a URL but the dedup key is empty: total_docs > 0 but unified empty."""
        doc = _search_doc("https://ok.com/page")
        data = [("q1", [doc], None)]
        with patch(f"{_MODULE}.url_dedup_key", return_value=""):
            urls, docs = combine_search_results_unified(data)
        assert len(docs) == 0
        assert len(urls) == 0
