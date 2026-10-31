"""Wiki search puts a page that spells the query's words exactly before one that only shares their stems."""

from __future__ import annotations

from pathlib import Path

from myrm_agent_harness.toolkits.wiki.core.config import WikiConfig
from myrm_agent_harness.toolkits.wiki.core.structure import WikiStructure
from myrm_agent_harness.toolkits.wiki.retrieval.exact_form import (
    MAX_REORDERED_ROWS,
    exact_form_terms,
    rank_exact_forms_first,
)
from myrm_agent_harness.toolkits.wiki.retrieval.indexer import WikiIndexer
from myrm_agent_harness.toolkits.wiki.retrieval.tokenizer import tokenize_for_fts

_QUERY = "transformers trained"
# Short and repetitive: bm25 scores it above a longer page that says the query's words once.
_STEMS_ONLY = "Transformer trains. Transformer trains. Transformer trains."
_EXACT = "Transformers trained on large datasets, then evaluated on many unrelated benchmarks across several languages."


def _page(body: str) -> str:
    return f"---\ntype: concept\n---\n\n## Compiled Truth\n{body}\n"


def _open(root: Path, *, public: Path | None = None) -> WikiIndexer:
    structure = WikiStructure(root, public_dirs=[public] if public else [])
    structure.ensure_structure()
    return WikiIndexer(structure, WikiConfig(enable_hybrid_search=False))


def _bm25_order(indexer: WikiIndexer, query: str) -> list[str]:
    """The order the match alone gives, before any exact-form ordering."""
    with indexer._get_conn() as conn:
        return [name for name, _ in indexer._query_fts(conn, tokenize_for_fts(query), 10, 0, frozenset())]


async def _names(indexer: WikiIndexer, query: str, *, limit: int = 10, offset: int = 0) -> list[str]:
    return [name for name, _ in await indexer.search(query, limit=limit, offset=offset)]


def test_only_plain_english_words_of_a_query_count_as_terms() -> None:
    assert exact_form_terms("Transformers, the 2024 training of c++ and gpt-4 知识图谱") == {
        "transformers",
        "training",
        "2024",
    }
    assert exact_form_terms("知识图谱") == frozenset()
    assert exact_form_terms("the how") == frozenset()


def test_a_candidate_that_spells_more_terms_comes_first_and_the_scores_stay_in_descending_order() -> None:
    candidates = [
        ("stems", 0.9, "Transformer trains"),
        ("one-word", 0.8, "Transformers train"),
        ("exact", 0.5, "Transformers trained"),
    ]

    ranked = rank_exact_forms_first(candidates, frozenset({"transformers", "trained"}))

    assert ranked == [("exact", 0.9), ("one-word", 0.8), ("stems", 0.5)]


def test_candidates_that_spell_the_same_number_of_terms_keep_their_score_order() -> None:
    candidates = [("a", 0.9, "transformers"), ("b", 0.8, "transformers"), ("c", 0.7, "transformer")]

    assert rank_exact_forms_first(candidates, frozenset({"transformers"})) == [("a", 0.9), ("b", 0.8), ("c", 0.7)]


def test_a_score_lowered_by_the_shared_library_decay_loses_a_tie_and_the_scores_are_handed_out_in_order() -> None:
    # The candidates arrive in match order, but a shared page's score carries the 0.9 decay, so the
    # score order is not the arrival order.
    candidates = [("shared", 0.63, "transformers"), ("primary", 0.70, "transformers"), ("stems", 0.65, "transformer")]

    assert rank_exact_forms_first(candidates, frozenset({"transformers"})) == [
        ("primary", 0.70),
        ("shared", 0.65),
        ("stems", 0.63),
    ]


def test_a_term_inside_a_longer_word_does_not_count() -> None:
    candidates = [("long-word", 0.9, "pretransformers"), ("whole-word", 0.5, "many-transformers here")]

    assert rank_exact_forms_first(candidates, frozenset({"transformers"}))[0][0] == "whole-word"


def test_a_single_candidate_is_returned_as_it_is() -> None:
    assert rank_exact_forms_first([("only", 0.4, "x")], frozenset({"x"})) == [("only", 0.4)]


def test_a_query_without_plain_words_leaves_the_order_of_the_candidates() -> None:
    assert rank_exact_forms_first([("a", 0.4, "x"), ("b", 0.9, "y")], frozenset()) == [("a", 0.4), ("b", 0.9)]


async def test_a_page_that_spells_the_query_exactly_comes_before_one_that_only_shares_the_stems(tmp_path: Path) -> None:
    indexer = _open(tmp_path / "vault")
    await indexer.upsert("stems-only", _page(_STEMS_ONLY))
    await indexer.upsert("exact", _page(_EXACT))
    assert _bm25_order(indexer, _QUERY) == ["stems-only", "exact"], "the match alone prefers the repetitive page"

    results = await indexer.search(_QUERY, limit=5)

    assert [name for name, _ in results] == ["exact", "stems-only"]
    scores = [score for _, score in results]
    assert scores == sorted(scores, reverse=True)
    assert all(0.0 < score < 1.0 for score in scores)


async def test_a_window_longer_than_the_limit_on_reordered_rows_keeps_the_order_of_the_match(tmp_path: Path) -> None:
    indexer = _open(tmp_path / "vault")
    await indexer.upsert("stems-only", _page(_STEMS_ONLY))
    await indexer.upsert("exact", _page(_EXACT))

    # A window is twice the limit plus the offset.
    assert await _names(indexer, _QUERY, limit=MAX_REORDERED_ROWS // 2) == ["exact", "stems-only"]
    assert await _names(indexer, _QUERY, limit=MAX_REORDERED_ROWS // 2 + 1) == ["stems-only", "exact"]
    assert await _names(indexer, _QUERY, limit=5, offset=MAX_REORDERED_ROWS) == []


async def test_a_negative_offset_is_read_as_zero(tmp_path: Path) -> None:
    indexer = _open(tmp_path / "vault")
    for i in range(3):
        await indexer.upsert(f"stems-{i}", _page(f"{_STEMS_ONLY} Note {i}."))
    for i in range(2):
        await indexer.upsert(f"exact-{i}", _page(f"{_EXACT} Note {i}."))

    results = await _names(indexer, _QUERY, limit=3, offset=-2)

    assert len(results) == 3
    assert results == await _names(indexer, _QUERY, limit=3)


async def test_a_page_that_spells_another_form_of_the_word_is_still_found(tmp_path: Path) -> None:
    indexer = _open(tmp_path / "vault")
    await indexer.upsert("stems-only", _page(_STEMS_ONLY))

    assert await _names(indexer, _QUERY) == ["stems-only"]


async def test_the_pages_of_a_result_list_are_slices_of_one_order(tmp_path: Path) -> None:
    indexer = _open(tmp_path / "vault")
    for i in range(3):
        await indexer.upsert(f"stems-{i}", _page(f"{_STEMS_ONLY} Note {i}."))
    for i in range(2):
        await indexer.upsert(f"exact-{i}", _page(f"{_EXACT} Note {i}."))
    assert _bm25_order(indexer, _QUERY)[0].startswith("stems"), "the match alone puts a repetitive page first"

    everything = await _names(indexer, _QUERY, limit=5)
    first_page = await _names(indexer, _QUERY, limit=3)
    second_page = await _names(indexer, _QUERY, limit=3, offset=3)

    assert sorted(everything[:2]) == ["exact-0", "exact-1"]
    assert first_page == everything[:3]
    assert second_page == everything[3:]


async def test_a_shared_page_that_spells_the_query_exactly_comes_before_a_local_page_that_only_shares_the_stems(
    tmp_path: Path,
) -> None:
    shared = _open(tmp_path / "shared")
    await shared.upsert("shared-exact", _page(_EXACT))
    local = _open(tmp_path / "local", public=tmp_path / "shared")
    await local.upsert("local-stems", _page(_STEMS_ONLY))

    assert await _names(local, _QUERY) == ["shared-exact", "local-stems"]


async def test_chinese_queries_keep_the_order_of_the_match(tmp_path: Path) -> None:
    indexer = _open(tmp_path / "vault")
    await indexer.upsert("graph-long", _page("知识图谱构建方法。" + "补充说明内容。" * 20))
    await indexer.upsert("graph-short", _page("知识图谱构建方法。"))
    await indexer.upsert("graph-mid", _page("知识图谱构建方法。" + "补充说明内容。" * 5))

    assert await _names(indexer, "知识图谱构建") == _bm25_order(indexer, "知识图谱构建")
