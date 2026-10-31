"""The pack injects only what answers the question, ranks it by how much of the question it answers, gives every page
one slot, scans markdown only for a vault whose index is unreadable or holds no pages, reads the same pages in every
listing order, and does not hold the turn or the event loop for a slow vault.

[INPUT]
- app.services.wiki.knowledge_pack.query_terms::carried_terms, paragraph_relevance, MAX_QUERY_CHARS
- app.services.wiki.knowledge_pack.schemas::KnowledgePackConfig
- app.services.wiki.knowledge_pack.selector::resolve_proactive_snippets_from_vaults
- myrm_agent_harness.toolkits.wiki.retrieval.indexer::WikiIndexer (POS: creates the index file on construction, filled or not)
- tests.support.knowledge_pack_vaults::make_vault, titles (POS: shared vault fixtures of the knowledge-pack tests)

[OUTPUT]
- Tests of the relevance floor (unit and through both retrieval tiers), of the ranking across vaults and across the
  pages of one vault, of the question length cap, of when the markdown scan runs and of the name order it reads its
  files in, and of the timeout against a slow scan.

[POS]
Relevance counterpart of the retrieval cases in ``test_knowledge_pack.py``.
"""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from typing import NoReturn

import pytest
from myrm_agent_harness.toolkits.wiki.core.config import WikiConfig
from myrm_agent_harness.toolkits.wiki.core.structure import WikiStructure
from myrm_agent_harness.toolkits.wiki.retrieval.indexer import WikiIndexer

from app.services.wiki.knowledge_pack import selector
from app.services.wiki.knowledge_pack.query_terms import MAX_QUERY_CHARS, carried_terms, paragraph_relevance
from app.services.wiki.knowledge_pack.schemas import KnowledgePackConfig
from app.services.wiki.knowledge_pack.selector import resolve_proactive_snippets_from_vaults
from tests.support.knowledge_pack_vaults import make_vault, titles

_TERMS = ["zurich", "office", "rules", "wifi", "desk"]


@pytest.mark.parametrize(
    ("terms", "title", "paragraph", "expected"),
    [
        (_TERMS, "Guide", "Nothing relevant here.", 0.0),
        (_TERMS, "Guide", "Wifi and desk booking.", 0.0),
        (_TERMS, "ZurichGuide", "Wifi codes rotate monthly.", 0.4),
        (_TERMS, "Guide", "Wifi desk and rules apply.", 0.6),
        (["budget"], "Guide", "Budget cap.", 1.0),
        (["budget", "limit"], "Guide", "Budget only.", 0.0),
        (["budget", "limit"], "Guide", "Budget limit.", 1.0),
        ([], "Guide", "Budget limit.", 0.0),
        (["me", "my", "budget"], "Memory", "Myrm budget notes.", 0.0),
    ],
    ids=[
        "none",
        "two-without-title",
        "two-with-title",
        "three",
        "single-term",
        "one-of-two",
        "two-of-two",
        "no-terms",
        "short-words-inside-longer-words",
    ],
)
def test_paragraph_relevance_floor(terms: list[str], title: str, paragraph: str, expected: float) -> None:
    """Two terms are the floor, three without a title hit; the score is the share of terms found."""
    assert paragraph_relevance(terms, title, paragraph) == pytest.approx(expected)


@pytest.mark.parametrize(
    ("terms", "text", "expected"),
    [
        (["me", "my"], "memory myrm", 0),
        (["me", "my"], "tell me about my plan", 2),
        (["agent"], "agents run", 1),
        (["age"], "agents run", 0),
        (["agents"], "one agent runs", 0),
        (["650"], "每晚650元", 1),
        (["clarify"], "structured_clarify", 1),
        (["向量", "数据"], "向量数据库", 2),
    ],
    ids=["inside-words", "whole-words", "word-start", "short-word-start", "longer-term", "digits-by-cjk", "underscore", "cjk"],
)
def test_carried_terms(terms: list[str], text: str, expected: int) -> None:
    """CJK terms are substrings; a word is a whole word, or from four characters the start of a longer one."""
    assert carried_terms(terms, text) == expected


@pytest.mark.asyncio
@pytest.mark.parametrize("indexed", [True, False], ids=["index-hit", "markdown-scan"])
async def test_question_the_vault_does_not_answer_injects_nothing(tmp_path: Path, indexed: bool) -> None:
    """One shared common word is enough for the index to rank a page first, and not enough to inject it."""
    vault = make_vault(
        tmp_path,
        "kb",
        {"HotelLimits": "Zephyr budget limit: hotel stays in Berlin are capped at 120 per night."},
        indexed=indexed,
    )

    assert await titles("can you write a budget plan for my birthday party", vault) == []
    assert await titles("what is the zephyr budget limit for hotel stays", vault) == ["HotelLimits"]


@pytest.mark.asyncio
@pytest.mark.parametrize("indexed", [True, False], ids=["index-hit", "markdown-scan"])
async def test_the_vault_that_answers_most_of_the_question_wins_whatever_the_vault_order(tmp_path: Path, indexed: bool) -> None:
    """The ranking comes from how much of the question a paragraph answers, not from which vault is listed first."""
    partial = make_vault(tmp_path, "partial", {"Partial": "zulu yankee xray notes"}, indexed=indexed)
    full = make_vault(tmp_path, "full", {"Full": "zulu yankee xray whiskey victor uniform notes"}, indexed=indexed)
    config = KnowledgePackConfig(pack_id="p", name="p", max_snippets=1)
    question = "zulu yankee xray whiskey victor uniform"

    assert await titles(question, partial, full, config=config) == ["Full"]
    assert await titles(question, full, partial, config=config) == ["Full"]


@pytest.mark.asyncio
@pytest.mark.parametrize("indexed", [True, False], ids=["index-hit", "markdown-scan"])
async def test_the_snippet_is_the_paragraph_that_carries_most_of_the_question(tmp_path: Path, indexed: bool) -> None:
    page = (
        "A long opening paragraph that says nothing about the subject, only filler to be the longest one on the page.\n\n"
        "Zephyr budget limit for hotels is 120 per night.\n\n"
        "A closing remark."
    )
    vault = make_vault(tmp_path, "kb", {"HotelLimits": page}, indexed=indexed)
    result = await resolve_proactive_snippets_from_vaults(
        "zephyr budget limit hotels", (vault,), {str(vault): "kb"}, timeout_seconds=2.0
    )

    assert [snippet.snippet for snippet in result.snippets] == ["Zephyr budget limit for hotels is 120 per night."]


@pytest.mark.asyncio
async def test_a_vault_whose_index_holds_pages_does_not_read_a_page_that_exists_only_as_a_file(tmp_path: Path) -> None:
    """The index answers for its vault, an empty answer included: listing a large vault to read fifteen pages is not free."""
    vault = make_vault(tmp_path, "kb", {"Indexed": "Alpha beta gamma notes."}, indexed=True)
    (vault / "wiki" / "concepts" / "OnDisk.md").write_text("Zephyr budget limit is 120 per night.", encoding="utf-8")

    assert await titles("zephyr budget limit", vault) == []


@pytest.mark.asyncio
async def test_a_vault_whose_index_was_created_but_never_filled_is_scanned_page_by_page(tmp_path: Path) -> None:
    """Any WikiIndexer creates its index file on construction, filled or not: the file alone must not silence the vault."""
    vault = make_vault(tmp_path, "kb", {"Policy": "Zephyr budget limit is 120 per night."}, indexed=False)
    WikiIndexer(WikiStructure(vault), WikiConfig(enable_hybrid_search=False))
    assert (vault / ".wiki_index.db").is_file()

    assert await titles("zephyr budget limit", vault) == ["Policy"]


@pytest.mark.asyncio
async def test_a_vault_with_an_unreadable_index_is_scanned_page_by_page_and_the_fallback_is_logged(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    vault = make_vault(tmp_path, "kb", {"Policy": "Zephyr budget limit is 120 per night."}, indexed=False)
    (vault / ".wiki_index.db").write_bytes(b"not a database")

    with caplog.at_level(logging.WARNING):
        injected = await titles("zephyr budget limit", vault)

    assert injected == ["Policy"]
    assert "falling back to markdown" in caplog.text


@pytest.mark.asyncio
async def test_a_failing_markdown_scan_injects_nothing_and_is_logged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    def fail(*_: object) -> NoReturn:
        raise OSError("disk gone")

    monkeypatch.setattr(selector, "_markdown_snippets", fail)
    vault = make_vault(tmp_path, "kb", {"Policy": "Zephyr budget limit is 120 per night."}, indexed=False)

    with caplog.at_level(logging.WARNING):
        injected = await titles("zephyr budget limit", vault)

    assert injected == []
    assert "markdown scan skipped" in caplog.text


@pytest.mark.asyncio
async def test_the_markdown_scan_picks_the_strongest_paragraph_of_all_pages_not_of_the_first_ones(tmp_path: Path) -> None:
    """Which pages come first by name must not decide which paragraph wins: only confidence does."""
    weak = [f"Zephyr budget limit memo {word}." for word in ("alpha", "bravo", "charlie", "delta", "echo", "foxtrot")]
    pages = {
        "a-notes": "\n\n".join(weak),
        "z-guide": "Zephyr budget limit memo golf.\n\nZephyr budget limit hotel berlin night rules.",
    }
    vault = make_vault(tmp_path, "kb", pages, indexed=False)
    config = KnowledgePackConfig(pack_id="p", name="p", max_snippets=1)

    assert await titles("zephyr budget limit hotel berlin night", vault, config=config) == ["z-guide"]


@pytest.mark.asyncio
async def test_only_the_start_of_a_very_long_question_is_read(tmp_path: Path) -> None:
    """Text beyond the cap neither costs scan time nor adds search terms."""
    vault = make_vault(tmp_path, "kb", {"Animals": "Quokka wombat dingo are marsupials."}, indexed=False)
    padding = "a " * MAX_QUERY_CHARS

    assert await titles("zephyr budget limit " + padding + "quokka wombat dingo", vault) == []
    assert await titles("quokka wombat dingo " + padding, vault) == ["Animals"]


@pytest.mark.asyncio
async def test_markdown_scan_reads_the_first_fifteen_files_by_name(tmp_path: Path) -> None:
    """Which pages the scan reads must not depend on the order the file system lists them in."""
    pages = {f"p{i:02d}": f"Zephyr budget limit w{i:02d}x." for i in reversed(range(20))}
    vault = make_vault(tmp_path, "kb", pages, indexed=False)

    assert await titles("zephyr budget limit", vault) == ["p00", "p01", "p02"]


@pytest.mark.asyncio
async def test_a_vault_whose_index_holds_only_raw_uploads_is_scanned_page_by_page(tmp_path: Path) -> None:
    """A raw upload waiting to be compiled is an index row, not an indexed page: it must not silence the vault."""
    vault = make_vault(tmp_path, "kb", {"Policy": "Zephyr budget limit is 120 per night."}, indexed=False)
    WikiIndexer(WikiStructure(vault), WikiConfig(enable_hybrid_search=False)).index_raw_text("upload", "quokka notes")

    assert await titles("zephyr budget limit", vault) == ["Policy"]


@pytest.mark.asyncio
@pytest.mark.parametrize("indexed", [True, False], ids=["index-hit", "markdown-scan"])
async def test_one_long_page_does_not_take_the_slots_of_the_pages_that_answer_other_parts(tmp_path: Path, indexed: bool) -> None:
    engine = [
        "Rocket engine thrust vector control uses hydraulic gimbal actuators on the nozzle.",
        "With rocket engine thrust vector control the flight computer samples attitude at 200 Hz.",
        "Rocket engine thrust vector control failures were traced to valve stiction in 2019 reviews.",
        "A rocket engine thrust vector control retrofit replaced hydraulics by electromechanical drives.",
    ]
    pages = {
        "a-engine": "\n\n".join(engine),
        "b-guidance": "Guidance computer limits engine thrust during ascent.",
        "c-staging": "Staging separation fires after rocket engine cutoff.",
    }
    vault = make_vault(tmp_path, "kb", pages, indexed=indexed)

    injected = await titles("rocket engine thrust vector control guidance staging", vault)

    assert sorted(injected) == ["a-engine", "b-guidance", "c-staging"]


@pytest.mark.asyncio
@pytest.mark.parametrize("indexed", [True, False], ids=["index-hit", "markdown-scan"])
async def test_the_paragraph_that_scores_highest_wins_over_the_one_with_more_words_of_its_own(
    tmp_path: Path, indexed: bool
) -> None:
    """The title counts for the page: a paragraph adding a term the title lacks answers more than one repeating it."""
    page = "Alpha gamma policy booking.\n\nAlpha gamma policy flights."
    vault = make_vault(tmp_path, "kb", {"booking-delta": page}, indexed=indexed)

    result = await resolve_proactive_snippets_from_vaults(
        "travel policy flights booking expense report", (vault,), {str(vault): "kb"}, timeout_seconds=2.0
    )

    assert [snippet.snippet for snippet in result.snippets] == ["Alpha gamma policy flights."]


@pytest.mark.asyncio
async def test_a_slow_vault_scan_neither_holds_the_turn_past_the_timeout_nor_stalls_the_event_loop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def slow_scan(*_: object) -> list[object]:
        time.sleep(0.8)
        return []

    monkeypatch.setattr(selector, "_markdown_snippets", slow_scan)
    vault = make_vault(tmp_path, "kb", {"Policy": "Zephyr budget limit is 120 per night."}, indexed=False)
    ticks: list[float] = []

    async def heartbeat() -> None:
        while True:
            ticks.append(time.monotonic())
            await asyncio.sleep(0.02)

    beat = asyncio.create_task(heartbeat())
    await asyncio.sleep(0.05)
    started = time.monotonic()
    result = await resolve_proactive_snippets_from_vaults(
        "zephyr budget limit", (vault,), {str(vault): "kb"}, timeout_seconds=0.15
    )
    elapsed = time.monotonic() - started
    await asyncio.sleep(0.05)
    beat.cancel()

    assert result.snippets == []
    assert elapsed < 0.6
    assert max(b - a for a, b in zip(ticks, ticks[1:], strict=False)) < 0.4


@pytest.mark.asyncio
@pytest.mark.parametrize("indexed", [True, False], ids=["index-hit", "markdown-scan"])
async def test_of_two_equally_relevant_paragraphs_the_first_is_the_snippet(tmp_path: Path, indexed: bool) -> None:
    vault = make_vault(tmp_path, "kb", {"Policy": "Zephyr budget limit alpha.\n\nZephyr budget limit bravo."}, indexed=indexed)

    result = await resolve_proactive_snippets_from_vaults(
        "zephyr budget limit", (vault,), {str(vault): "kb"}, timeout_seconds=2.0
    )

    assert [snippet.snippet for snippet in result.snippets] == ["Zephyr budget limit alpha."]
