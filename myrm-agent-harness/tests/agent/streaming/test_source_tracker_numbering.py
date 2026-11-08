"""Tests for SourceTracker numbering: the number a page is shown under is the index of its card.

A tool numbers the sources in its result before the stream knows them (``index_for``), and the cards are issued later
(``add_batch``), after citation normalization may have rewritten a URL. The number the model read must come back as
the card's index, whatever happened to the URL in between.

Covers:
- index_for: one page keeps one number for the whole run
- add_batch: a reserved number becomes the card index, also for a rewritten URL (``redirect_url``)
- two reserved spellings that normalize to one URL keep two cards
- invariants over randomized runs (fixed seeds)
"""

from __future__ import annotations

import random

import pytest

from myrm_agent_harness.agent.streaming.source_tracker import SourceTracker
from myrm_agent_harness.toolkits.web_search.processing.citation_resolver import strip_tracking_parameters
from myrm_agent_harness.utils.url_utils import url_dedup_key


class TestIndexFor:
    def test_numbers_follow_first_use(self) -> None:
        tracker = SourceTracker()
        assert tracker.index_for({"url": "https://a.com"}) == 1
        assert tracker.index_for({"url": "https://b.com"}) == 2

    @pytest.mark.parametrize("spelling", ["https://www.a.com/x/", "https://A.com/x", "https://a.com/x"])
    def test_one_page_keeps_one_number(self, spelling: str) -> None:
        tracker = SourceTracker()
        assert tracker.index_for({"url": "https://a.com/x"}) == 1
        assert tracker.index_for({"url": spelling}) == 1

    def test_pages_that_differ_get_different_numbers(self) -> None:
        tracker = SourceTracker()
        assert tracker.index_for({"url": "https://a.com/x#s1"}) != tracker.index_for({"url": "https://a.com/x#s2"})

    def test_asking_emits_nothing_and_a_later_batch_still_numbers_after_it(self) -> None:
        tracker = SourceTracker()
        tracker.index_for({"url": "https://a.com"})
        batch = tracker.add_batch([{"url": "https://z.com"}])
        assert [s["index"] for s in batch] == [2]


class TestReservedNumbersBecomeCardIndexes:
    def test_the_card_takes_the_reserved_number_not_its_position(self) -> None:
        tracker = SourceTracker()
        tracker.index_for({"url": "https://b.com"})
        tracker.index_for({"url": "https://a.com"})
        batch = tracker.add_batch([{"url": "https://a.com"}, {"url": "https://b.com"}])
        assert [(s["url"], s["index"]) for s in batch] == [("https://a.com", 2), ("https://b.com", 1)]

    def test_a_later_call_continues_the_numbering_and_a_known_page_keeps_its_number(self) -> None:
        tracker = SourceTracker()
        for url in ("https://a.com", "https://b.com"):
            tracker.index_for({"url": url})
        tracker.add_batch([{"url": "https://a.com"}, {"url": "https://b.com"}])

        assert tracker.index_for({"url": "https://b.com"}) == 2
        assert tracker.index_for({"url": "https://c.com"}) == 3
        batch = tracker.add_batch([{"url": "https://b.com"}, {"url": "https://c.com"}])
        assert [(s["url"], s["index"]) for s in batch] == [("https://c.com", 3)]

    def test_a_reserved_number_gets_one_card(self) -> None:
        tracker = SourceTracker()
        tracker.index_for({"url": "https://a.com"})
        assert len(tracker.add_batch([{"url": "https://a.com"}])) == 1
        assert tracker.add_batch([{"url": "https://a.com"}]) == []

    def test_a_source_nobody_numbered_takes_the_next_free_number(self) -> None:
        tracker = SourceTracker()
        tracker.index_for({"url": "https://a.com"})
        assert [s["index"] for s in tracker.add_batch([{"url": "https://z.com"}])] == [2]

    def test_a_source_without_a_url_is_numbered_by_its_content(self) -> None:
        tracker = SourceTracker()
        entry: dict[str, object] = {"url": "", "title": "Notes", "snippet": "s", "date": ""}
        number = tracker.index_for(entry)
        assert [s["index"] for s in tracker.add_batch([dict(entry)])] == [number]


class TestRewrittenUrls:
    """Citation normalization runs after the numbers were handed out and rewrites ``url``."""

    def test_the_card_of_a_rewritten_url_has_the_number_the_model_read(self) -> None:
        tracker = SourceTracker()
        shown = "https://x.com/a?utm_source=t"
        number = tracker.index_for({"url": shown})
        batch = tracker.add_batch([{"url": "https://x.com/a", "redirect_url": shown}])
        assert [(s["url"], s["index"]) for s in batch] == [("https://x.com/a", number)]

    def test_the_clean_spelling_of_a_page_that_was_rewritten_has_the_same_number(self) -> None:
        tracker = SourceTracker()
        number = tracker.index_for({"url": "https://x.com/a?utm_source=t"})
        tracker.add_batch([{"url": "https://x.com/a", "redirect_url": "https://x.com/a?utm_source=t"}])
        assert tracker.index_for({"url": "https://x.com/a"}) == number

    def test_two_spellings_that_normalize_to_one_url_keep_two_cards(self) -> None:
        tracker = SourceTracker()
        first, second = "https://x.com/a?utm_source=t", "https://x.com/a?utm_source=u"
        numbers = [tracker.index_for({"url": first}), tracker.index_for({"url": second})]
        batch = tracker.add_batch(
            [
                {"url": "https://x.com/a", "redirect_url": first},
                {"url": "https://x.com/a", "redirect_url": second},
            ]
        )
        assert [s["index"] for s in batch] == numbers
        # A merge by URL, in the server or the client, would fold two cards of one URL and leave a number unanswered.
        assert len({s["url"] for s in batch}) == 2

    def test_a_redirect_that_was_never_numbered_dedups_by_its_final_url(self) -> None:
        tracker = SourceTracker()
        assert len(tracker.add_batch([{"url": "https://x.com/a", "redirect_url": "https://r.example/1"}])) == 1
        assert tracker.add_batch([{"url": "https://x.com/a", "redirect_url": "https://r.example/2"}]) == []


_PAGES = [f"https://site{n}.example/page" for n in range(6)]
# Spellings that tracking-parameter stripping (and the same-page key) bring back to the page itself.
_SPELLINGS = ("{}", "{}?utm_source=feed", "{}/?utm_medium=mail", "{}?utm_campaign=x&utm_term=y")


def _one_call(tracker: SourceTracker, shown: list[str]) -> tuple[dict[str, int], list[dict[str, object]]]:
    """A tool call as the run sees it: numbers handed out per shown URL, then normalized sources become cards."""
    urls = list(dict.fromkeys(shown))
    labels = {url: tracker.index_for({"url": url}) for url in urls}
    sources: list[dict[str, object]] = []
    for url in urls:
        clean = strip_tracking_parameters(url)
        sources.append({"url": clean} if clean == url else {"url": clean, "redirect_url": url})
    return labels, tracker.add_batch(sources)


def _same_page(first: str, second: str) -> bool:
    return url_dedup_key(strip_tracking_parameters(first), keep_fragment=True) == url_dedup_key(
        strip_tracking_parameters(second), keep_fragment=True
    )


@pytest.mark.parametrize("seed", range(200))
def test_every_number_the_model_read_names_the_card_of_that_page(seed: int) -> None:
    rng = random.Random(seed)
    tracker = SourceTracker()
    cards: dict[int, dict[str, object]] = {}
    for _ in range(rng.randint(1, 5)):
        shown = [rng.choice(_SPELLINGS).format(rng.choice(_PAGES)) for _ in range(rng.randint(1, 5))]
        labels, batch = _one_call(tracker, shown)
        for card in batch:
            index = card["index"]
            assert isinstance(index, int)
            assert index not in cards, "a number must get one card"
            cards[index] = card

        for url, number in labels.items():
            card = cards.get(number)
            assert card is not None, f"number {number} shown for {url} has no card"
            assert isinstance(card["url"], str)
            assert _same_page(card["url"], url), f"number {number}: shown {url}, card {card['url']}"
        assert len({card["url"] for card in cards.values()}) == len(cards), "cards of one URL would be merged"
