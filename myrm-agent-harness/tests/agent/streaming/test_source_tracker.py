"""Tests for SourceTracker — per-run source deduplication and indexing.

Covers:
- URL-based deduplication (spellings of one page are one source; anything that tells pages apart stays apart)
- Content-hash-based deduplication (non-URL sources)
- Index assignment
- Incremental return (add_batch returns only new items)
- Entries that are not dicts are skipped

Numbering a source before its card exists (``index_for``) is covered in test_source_tracker_numbering.py.
"""

from __future__ import annotations

from typing import cast

import pytest

from myrm_agent_harness.agent.streaming.source_tracker import SourceTracker


class TestSourceTrackerDedup:
    """URL and content-based deduplication."""

    def test_url_dedup(self) -> None:
        tracker = SourceTracker()
        batch1 = tracker.add_batch(
            [
                {"url": "https://a.com", "title": "A"},
                {"url": "https://b.com", "title": "B"},
            ]
        )
        assert len(batch1) == 2

        batch2 = tracker.add_batch(
            [
                {"url": "https://a.com", "title": "A duplicate"},
            ]
        )
        assert len(batch2) == 0

    def test_content_hash_dedup_for_non_url_sources(self) -> None:
        tracker = SourceTracker()
        batch1 = tracker.add_batch(
            [
                {"type": "mcp", "skill_name": "web_search"},
            ]
        )
        assert len(batch1) == 1

        batch2 = tracker.add_batch(
            [
                {"type": "mcp", "skill_name": "web_search"},
            ]
        )
        assert len(batch2) == 0

    def test_different_content_not_deduped(self) -> None:
        tracker = SourceTracker()
        batch = tracker.add_batch(
            [
                {"type": "mcp", "skill_name": "web_search"},
                {"type": "mcp", "skill_name": "code_exec"},
            ]
        )
        assert len(batch) == 2

    def test_source_key_dedup(self) -> None:
        tracker = SourceTracker()
        batch1 = tracker.add_batch(
            [
                {
                    "type": "knowledge",
                    "kb_name": "LLM-Wiki",
                    "source_key": "kb:LLM-Wiki:concepts/budget:claim:c1:evidence:raw/a.md:1-2",
                    "snapshot_status": "stale",
                }
            ]
        )
        assert len(batch1) == 1

        batch2 = tracker.add_batch(
            [
                {
                    "type": "knowledge",
                    "kb_name": "LLM-Wiki",
                    "source_key": "kb:LLM-Wiki:concepts/budget:claim:c1:evidence:raw/a.md:1-2",
                    "snapshot_status": "verified",
                }
            ]
        )
        assert len(batch2) == 0


class TestSourceTrackerSamePage:
    """A page spelled two ways is one source; anything that tells pages apart stays apart."""

    @pytest.mark.parametrize(
        ("first", "second"),
        [
            ("https://example.com/docs/", "https://example.com/docs"),
            ("https://www.example.com/a", "https://example.com/a"),
            ("https://Example.com/a", "https://example.com/a"),
            ("https://en.wikipedia.org/wiki/Foo_(bar)", "https://en.wikipedia.org/wiki/Foo_%28bar%29"),
            ("https://www.bilibili.com/video/BV1xx411c7mD/", "https://www.bilibili.com/video/BV1xx411c7mD"),
            ("https://example.com/a#s1", "https://Example.com/a#s1"),
            ("https://example.com", "https://example.com/"),
            ("https://example.com?q=1", "https://example.com/?q=1"),
            ("https://example.com#s1", "https://example.com/#s1"),
        ],
    )
    def test_spellings_of_one_page_dedup_across_batches(self, first: str, second: str) -> None:
        tracker = SourceTracker()
        assert len(tracker.add_batch([{"url": first}])) == 1
        assert tracker.add_batch([{"url": second}]) == []

    @pytest.mark.parametrize(
        ("first", "second"),
        [
            ("https://example.com/a#s1", "https://example.com/a#s2"),
            ("https://example.com/a", "https://example.com/a#s1"),
            ("http://example.com/a", "https://example.com/a"),
            ("https://example.com/a", "https://example.com/b"),
            ("https://example.com/a?x=1", "https://example.com/a?x=2"),
            ("https://example.com#s1", "https://example.com/#s2"),
        ],
    )
    def test_pages_that_differ_stay_separate(self, first: str, second: str) -> None:
        tracker = SourceTracker()
        tracker.add_batch([{"url": first}])
        assert len(tracker.add_batch([{"url": second}])) == 1

    def test_a_url_that_is_not_text_falls_back_to_the_content_hash(self) -> None:
        tracker = SourceTracker()
        source: dict[str, object] = {"url": 5, "title": "T"}
        assert len(tracker.add_batch([source])) == 1
        assert tracker.add_batch([source]) == []


class TestSourceTrackerIndex:
    """Index assignment."""

    def test_sequential_index(self) -> None:
        tracker = SourceTracker()
        batch = tracker.add_batch(
            [
                {"url": "https://a.com"},
                {"url": "https://b.com"},
                {"url": "https://c.com"},
            ]
        )
        assert [s["index"] for s in batch] == [1, 2, 3]

    def test_index_persists_across_batches(self) -> None:
        tracker = SourceTracker()
        tracker.add_batch([{"url": "https://a.com"}])
        batch2 = tracker.add_batch([{"url": "https://b.com"}])
        assert batch2[0]["index"] == 2

    def test_deduped_items_dont_consume_index(self) -> None:
        tracker = SourceTracker()
        tracker.add_batch([{"url": "https://a.com"}])
        tracker.add_batch([{"url": "https://a.com"}])  # dedup
        batch3 = tracker.add_batch([{"url": "https://b.com"}])
        assert batch3[0]["index"] == 2  # not 3


class TestSourceTrackerIncremental:
    """add_batch returns only new items."""

    def test_incremental_return(self) -> None:
        tracker = SourceTracker()
        batch1 = tracker.add_batch(
            [
                {"url": "https://a.com"},
                {"url": "https://b.com"},
            ]
        )
        assert len(batch1) == 2

        batch2 = tracker.add_batch(
            [
                {"url": "https://a.com"},
                {"url": "https://c.com"},
            ]
        )
        assert len(batch2) == 1
        assert batch2[0]["url"] == "https://c.com"

    def test_url_dedup_after_citation_normalization(self) -> None:
        """Two provider redirects resolving to the same final URL should dedup."""
        tracker = SourceTracker()
        batch1 = tracker.add_batch(
            [
                {
                    "url": "https://real.example/article",
                    "redirect_url": "https://redirect-a.example/r",
                    "title": "A",
                },
            ]
        )
        assert len(batch1) == 1

        batch2 = tracker.add_batch(
            [
                {
                    "url": "https://real.example/article",
                    "redirect_url": "https://redirect-b.example/r",
                    "title": "B",
                },
            ]
        )
        assert len(batch2) == 0


class TestSourceTrackerBatchInput:
    """What add_batch accepts."""

    def test_empty_batch_adds_nothing(self) -> None:
        tracker = SourceTracker()
        assert tracker.add_batch([]) == []

    def test_non_dict_items_skipped(self) -> None:
        tracker = SourceTracker()
        entries = cast("list[dict[str, object]]", ["not_a_dict", 42, None, {"url": "https://a.com"}])
        assert len(tracker.add_batch(entries)) == 1


class TestSourceTrackerEdgeCases:
    """Edge cases and robustness."""

    def test_url_with_fragment_not_deduped(self) -> None:
        """URLs with different fragments are treated as different."""
        tracker = SourceTracker()
        batch = tracker.add_batch(
            [
                {"url": "https://a.com/page#section1"},
                {"url": "https://a.com/page#section2"},
            ]
        )
        assert len(batch) == 2

    def test_mixed_url_and_non_url_sources(self) -> None:
        tracker = SourceTracker()
        batch = tracker.add_batch(
            [
                {"url": "https://a.com"},
                {"type": "mcp", "skill_name": "web_search"},
                {"type": "conversation_history", "title": "Chat 1"},
                {"url": "https://b.com"},
            ]
        )
        assert len(batch) == 4
        assert [s["index"] for s in batch] == [1, 2, 3, 4]

    def test_large_batch_performance(self) -> None:
        """Verify no performance degradation with larger batches."""
        tracker = SourceTracker()
        sources: list[dict[str, object]] = [{"url": f"https://example{i}.com"} for i in range(100)]
        batch = tracker.add_batch(sources)
        assert len(batch) == 100
        assert batch[-1]["index"] == 100

    def test_source_preserves_original_fields(self) -> None:
        tracker = SourceTracker()
        batch = tracker.add_batch(
            [
                {
                    "url": "https://a.com",
                    "title": "Test",
                    "snippet": "Some text",
                    "extra_field": 42,
                },
            ]
        )
        assert batch[0]["title"] == "Test"
        assert batch[0]["snippet"] == "Some text"
        assert batch[0]["extra_field"] == 42
        assert batch[0]["index"] == 1

    def test_index_field_in_input_ignored_for_dedup(self) -> None:
        """Input index field should not affect content-hash dedup."""
        tracker = SourceTracker()
        batch1 = tracker.add_batch([{"type": "mcp", "skill_name": "test", "index": 99}])
        assert len(batch1) == 1
        assert batch1[0]["index"] == 1  # overwritten by tracker

        batch2 = tracker.add_batch([{"type": "mcp", "skill_name": "test", "index": 100}])
        assert len(batch2) == 0  # deduped (index excluded from hash)
