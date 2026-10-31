"""The pack injects only what answers the question, ranks it by how much of the question it answers, scans markdown
only for a vault without a readable index, and reads the same pages in every listing order.

[INPUT]
- app.services.wiki.knowledge_pack.query_terms::carried_terms, paragraph_relevance, MAX_QUERY_CHARS
- app.services.wiki.knowledge_pack.schemas::KnowledgePackConfig
- app.services.wiki.knowledge_pack.selector::resolve_proactive_snippets_from_vaults, _markdown_snippets
- myrm_agent_harness.toolkits.retriever.cjk_tokenizer::build_cjk_index_segment (POS: writes the CJK search column the way the index does)

[OUTPUT]
- Tests of the relevance floor (unit and through both retrieval tiers), of the ranking across vaults, of the question
  length cap, of when the markdown scan runs and of the name order it reads its files in.

[POS]
Relevance counterpart of the retrieval cases in ``test_knowledge_pack.py``.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from pathlib import Path

import pytest
from myrm_agent_harness.toolkits.retriever.cjk_tokenizer import build_cjk_index_segment

from app.services.wiki.knowledge_pack import selector
from app.services.wiki.knowledge_pack.query_terms import MAX_QUERY_CHARS, carried_terms, paragraph_relevance
from app.services.wiki.knowledge_pack.schemas import KnowledgePackConfig, RelevantSnippet
from app.services.wiki.knowledge_pack.selector import resolve_proactive_snippets_from_vaults

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


def _make_vault(root: Path, name: str, pages: dict[str, str], *, indexed: bool) -> Path:
    """A vault holding the given page files; with `indexed`, every page also gets a row in the FTS index."""
    vault = root / name
    concepts = vault / "wiki" / "concepts"
    concepts.mkdir(parents=True)
    for page_name, text in pages.items():
        (concepts / f"{page_name}.md").write_text(text, encoding="utf-8")
    if indexed:
        with sqlite3.connect(vault / ".wiki_index.db") as conn:
            conn.execute(
                'CREATE VIRTUAL TABLE wiki_fts USING fts5(concept_name, truth_content, tokenize="unicode61 remove_diacritics 1")'
            )
            conn.executemany(
                "INSERT INTO wiki_fts(concept_name, truth_content) VALUES (?, ?)",
                [(page_name, build_cjk_index_segment(text)) for page_name, text in pages.items()],
            )
    return vault


async def _titles(query: str, *vaults: Path, config: KnowledgePackConfig | None = None) -> list[str]:
    result = await resolve_proactive_snippets_from_vaults(
        query,
        vaults,
        {str(v): v.name for v in vaults},
        config=config,
        timeout_seconds=2.0,
    )
    return [snippet.article_title for snippet in result.snippets]


@pytest.mark.asyncio
@pytest.mark.parametrize("indexed", [True, False], ids=["index-hit", "markdown-scan"])
async def test_question_the_vault_does_not_answer_injects_nothing(tmp_path: Path, indexed: bool) -> None:
    """One shared common word is enough for the index to rank a page first, and not enough to inject it."""
    vault = _make_vault(
        tmp_path,
        "kb",
        {"HotelLimits": "Zephyr budget limit: hotel stays in Berlin are capped at 120 per night."},
        indexed=indexed,
    )

    assert await _titles("can you write a budget plan for my birthday party", vault) == []
    assert await _titles("what is the zephyr budget limit for hotel stays", vault) == ["HotelLimits"]


@pytest.mark.asyncio
@pytest.mark.parametrize("indexed", [True, False], ids=["index-hit", "markdown-scan"])
async def test_the_vault_that_answers_most_of_the_question_wins_whatever_the_vault_order(tmp_path: Path, indexed: bool) -> None:
    """The ranking comes from how much of the question a paragraph answers, not from which vault is listed first."""
    partial = _make_vault(tmp_path, "partial", {"Partial": "zulu yankee xray notes"}, indexed=indexed)
    full = _make_vault(tmp_path, "full", {"Full": "zulu yankee xray whiskey victor uniform notes"}, indexed=indexed)
    config = KnowledgePackConfig(pack_id="p", name="p", max_snippets=1)
    question = "zulu yankee xray whiskey victor uniform"

    assert await _titles(question, partial, full, config=config) == ["Full"]
    assert await _titles(question, full, partial, config=config) == ["Full"]


@pytest.mark.asyncio
@pytest.mark.parametrize("indexed", [True, False], ids=["index-hit", "markdown-scan"])
async def test_the_snippet_is_the_paragraph_that_carries_most_of_the_question(tmp_path: Path, indexed: bool) -> None:
    page = (
        "A long opening paragraph that says nothing about the subject, only filler to be the longest one on the page.\n\n"
        "Zephyr budget limit for hotels is 120 per night.\n\n"
        "A closing remark."
    )
    vault = _make_vault(tmp_path, "kb", {"HotelLimits": page}, indexed=indexed)
    result = await resolve_proactive_snippets_from_vaults(
        "zephyr budget limit hotels", (vault,), {str(vault): "kb"}, timeout_seconds=2.0
    )

    assert [snippet.snippet for snippet in result.snippets] == ["Zephyr budget limit for hotels is 120 per night."]


@pytest.mark.asyncio
async def test_a_vault_with_a_readable_index_is_never_scanned_page_by_page(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The index answers for its vault, an empty answer included: listing a large vault to read fifteen pages is not free."""
    scanned: list[Path] = []

    def record_scan(vault: Path, label: str, terms: Sequence[str]) -> list[RelevantSnippet]:
        scanned.append(vault)
        return []

    monkeypatch.setattr(selector, "_markdown_snippets", record_scan)
    vault = _make_vault(tmp_path, "kb", {"Indexed": "Alpha beta gamma notes."}, indexed=True)

    assert await _titles("zephyr budget limit", vault) == []
    assert scanned == []


@pytest.mark.asyncio
async def test_a_vault_with_an_unreadable_index_is_scanned_page_by_page(tmp_path: Path) -> None:
    vault = _make_vault(tmp_path, "kb", {"Policy": "Zephyr budget limit is 120 per night."}, indexed=False)
    (vault / ".wiki_index.db").write_bytes(b"not a database")

    assert await _titles("zephyr budget limit", vault) == ["Policy"]


@pytest.mark.asyncio
async def test_only_the_start_of_a_very_long_question_is_read(tmp_path: Path) -> None:
    """Text beyond the cap neither costs scan time nor adds search terms."""
    vault = _make_vault(tmp_path, "kb", {"Animals": "Quokka wombat dingo are marsupials."}, indexed=False)
    padding = "a " * MAX_QUERY_CHARS

    assert await _titles("zephyr budget limit " + padding + "quokka wombat dingo", vault) == []
    assert await _titles("quokka wombat dingo " + padding, vault) == ["Animals"]


@pytest.mark.asyncio
async def test_markdown_scan_reads_the_first_fifteen_files_by_name(tmp_path: Path) -> None:
    """Which pages the scan reads must not depend on the order the file system lists them in."""
    pages = {f"p{i:02d}": f"Zephyr budget limit w{i:02d}x." for i in reversed(range(20))}
    vault = _make_vault(tmp_path, "kb", pages, indexed=False)

    assert await _titles("zephyr budget limit", vault) == ["p00", "p01", "p02"]
