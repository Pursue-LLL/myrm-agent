"""Tests for MMR (Maximal Marginal Relevance) diversity reranking in MemoryRetriever."""

import random

import pytest

from myrm_agent_harness.toolkits.memory.config import RetrievalConfig
from myrm_agent_harness.toolkits.memory.retriever import MemoryRetriever, _jaccard_similarity
from myrm_agent_harness.toolkits.memory.text_utils import tokenize
from myrm_agent_harness.toolkits.memory.types import MemorySearchResult, MemoryType, SemanticMemory


def _make_result(content: str, score: float, mem_id: str = "") -> MemorySearchResult:
    mem = SemanticMemory(content=content, importance=0.5)
    if mem_id:
        mem.id = mem_id
    return MemorySearchResult(memory=mem, score=score, memory_type=MemoryType.SEMANTIC)


class TestTokenize:
    def test_basic_english(self) -> None:
        tokens = tokenize("Hello World")
        assert tokens == frozenset({"hello", "world"})

    def test_case_insensitive(self) -> None:
        assert tokenize("Python") == tokenize("python")

    def test_empty_string(self) -> None:
        assert tokenize("") == frozenset()

    def test_mixed_language(self) -> None:
        tokens = tokenize("用户 喜欢 Python")
        assert "python" in tokens
        assert "用户" in tokens


class TestJaccardSimilarity:
    def test_identical_sets(self) -> None:
        a = frozenset({"a", "b", "c"})
        assert _jaccard_similarity(a, a) == 1.0

    def test_disjoint_sets(self) -> None:
        a = frozenset({"a", "b"})
        b = frozenset({"c", "d"})
        assert _jaccard_similarity(a, b) == 0.0

    def test_partial_overlap(self) -> None:
        a = frozenset({"a", "b", "c"})
        b = frozenset({"b", "c", "d"})
        assert _jaccard_similarity(a, b) == 2.0 / 4.0

    def test_empty_set(self) -> None:
        assert _jaccard_similarity(frozenset(), frozenset({"a"})) == 0.0
        assert _jaccard_similarity(frozenset(), frozenset()) == 0.0

    def test_symmetric(self) -> None:
        a = frozenset({"x", "y"})
        b = frozenset({"y", "z"})
        assert _jaccard_similarity(a, b) == _jaccard_similarity(b, a)


class TestMMRSelect:
    def test_mmr_disabled_when_lambda_1(self) -> None:
        """λ=1.0 should return all candidates unchanged."""
        config = RetrievalConfig(mmr_lambda=1.0, min_relevance_score=0.0)
        retriever = MemoryRetriever(config)

        results = [
            _make_result("same content here", 0.9, "a"),
            _make_result("same content here", 0.8, "b"),
        ]
        ranked = retriever.rank(results, limit=2)
        assert len(ranked) == 2

    def test_mmr_promotes_diversity(self) -> None:
        """MMR should prefer diverse results over similar high-scoring ones."""
        config = RetrievalConfig(mmr_lambda=0.5, min_relevance_score=0.0)
        retriever = MemoryRetriever(config)

        results = [
            _make_result("user likes Python programming language", 0.95, "a"),
            _make_result("user likes Python coding style", 0.90, "b"),
            _make_result("user prefers dark theme in editor", 0.85, "c"),
        ]
        ranked = retriever.rank(results, limit=2)

        ids = {r.id for r in ranked}
        assert "a" in ids
        assert "c" in ids

    def test_mmr_preserves_top_result(self) -> None:
        """The highest-scoring result should always be selected first."""
        config = RetrievalConfig(mmr_lambda=0.3, min_relevance_score=0.0)
        retriever = MemoryRetriever(config)

        results = [
            _make_result("top result unique content", 0.99, "top"),
            _make_result("other result different topic", 0.50, "other"),
        ]
        ranked = retriever.rank(results, limit=2)
        assert ranked[0].id == "top"

    def test_mmr_with_all_identical_content(self) -> None:
        """When all content is identical, MMR should still return limit results."""
        config = RetrievalConfig(mmr_lambda=0.7, min_relevance_score=0.0)
        retriever = MemoryRetriever(config)

        results = [
            _make_result("identical content", 0.9, "a"),
            _make_result("identical content", 0.8, "b"),
            _make_result("identical content", 0.7, "c"),
        ]
        ranked = retriever.rank(results, limit=3)
        assert len(ranked) == 3

    def test_mmr_fewer_candidates_than_limit(self) -> None:
        """When candidates < limit, all should be returned."""
        config = RetrievalConfig(mmr_lambda=0.7, min_relevance_score=0.0)
        retriever = MemoryRetriever(config)

        results = [_make_result("content", 0.9, "a")]
        ranked = retriever.rank(results, limit=5)
        assert len(ranked) == 1

    def test_mmr_with_fuse(self) -> None:
        """MMR should also work through the fuse() path."""
        config = RetrievalConfig(mmr_lambda=0.5, min_relevance_score=0.0)
        retriever = MemoryRetriever(config)

        list1 = [
            _make_result("Python web framework Flask", 0.9, "a"),
            _make_result("Python web framework Django", 0.85, "b"),
        ]
        list2 = [
            _make_result("Rust systems programming", 0.8, "c"),
        ]
        fused = retriever.fuse([list1, list2], limit=2)
        assert len(fused) == 2

    def test_mmr_default_lambda(self) -> None:
        """Default config should have mmr_lambda=0.7."""
        config = RetrievalConfig()
        assert config.mmr_lambda == 0.7

    def test_mmr_empty_results(self) -> None:
        config = RetrievalConfig(mmr_lambda=0.5, min_relevance_score=0.0)
        retriever = MemoryRetriever(config)
        assert retriever.rank([], limit=5) == []

    def test_mmr_diverse_topics_selected(self) -> None:
        """With 5 candidates across 3 topics, MMR should pick from each topic."""
        config = RetrievalConfig(mmr_lambda=0.5, min_relevance_score=0.0)
        retriever = MemoryRetriever(config)

        results = [
            _make_result("user prefers Python for backend development", 0.95, "py1"),
            _make_result("user prefers Python for scripting tasks", 0.93, "py2"),
            _make_result("user likes TypeScript for frontend work", 0.88, "ts1"),
            _make_result("user likes TypeScript for React projects", 0.86, "ts2"),
            _make_result("user enjoys Rust for systems programming", 0.80, "rs1"),
        ]
        ranked = retriever.rank(results, limit=3)
        ids = {r.id for r in ranked}

        assert "py1" in ids
        assert "ts1" in ids or "rs1" in ids
        assert len(ids) == 3

    def test_mmr_scores_normalized(self) -> None:
        """Output scores should be normalized to [0, 1]."""
        config = RetrievalConfig(mmr_lambda=0.7, min_relevance_score=0.0)
        retriever = MemoryRetriever(config)

        results = [
            _make_result("content alpha", 0.9, "a"),
            _make_result("content beta", 0.5, "b"),
        ]
        ranked = retriever.rank(results, limit=2)
        for r in ranked:
            assert 0.0 <= r.score <= 1.0
        assert ranked[0].score == 1.0


_VOCAB = ("alpha", "beta", "gamma", "delta", "epsilon", "zeta", "eta", "theta", "iota", "kappa")
_SOURCES = (None, "chat-1", "chat-2", "chat-3")
_RELEVANCE = (0.9, 0.7, 0.7, 0.5, 0.5, 0.3)  # repeated values force ties


def _sourced_result(content: str, mem_id: str, source_chat_id: str | None) -> MemorySearchResult:
    mem = SemanticMemory(content=content, importance=0.5, source_chat_id=source_chat_id)
    mem.id = mem_id
    return MemorySearchResult(memory=mem, score=0.5, memory_type=MemoryType.SEMANTIC)


def _reference_mmr_select(
    lam: float,
    source_weight: float,
    scores: dict[str, float],
    items: dict[str, MemorySearchResult],
    limit: int,
) -> list[str]:
    """MMR straight from its definition: every pick rescans the whole selected set."""
    top = max(scores.values())
    relevance = {mid: s / top for mid, s in scores.items()}
    tokens = {mid: tokenize(items[mid].content) for mid in scores}
    selected: list[str] = []
    while len(selected) < min(limit, len(scores)):
        best_id, best_mmr = "", float("-inf")
        for mid in scores:
            if mid in selected:
                continue
            content_sim = max((_jaccard_similarity(tokens[mid], tokens[chosen]) for chosen in selected), default=0.0)
            source_id = items[mid].memory.source_chat_id
            source_penalty = 0.0
            if source_weight > 0 and selected and source_id:
                same_source = sum(1 for chosen in selected if items[chosen].memory.source_chat_id == source_id)
                source_penalty = source_weight * (same_source / len(selected))
            mmr = lam * relevance[mid] - (1.0 - lam) * (content_sim + source_penalty)
            if mmr > best_mmr:
                best_id, best_mmr = mid, mmr
        selected.append(best_id)
    return selected


class TestMMRSelectMatchesDefinition:
    @pytest.mark.parametrize("seed", range(40))
    def test_incremental_selection_equals_full_rescan(self, seed: int) -> None:
        """Random pools with tied relevance, shared sources and overlapping vocabulary."""
        rng = random.Random(seed)
        results = [
            _sourced_result(" ".join(rng.sample(_VOCAB, k=rng.randint(1, 5))), f"m{i}", rng.choice(_SOURCES))
            for i in range(rng.randint(4, 30))
        ]
        items = {r.id: r for r in results}
        scores = {r.id: rng.choice(_RELEVANCE) for r in results}

        for lam in (0.0, 0.3, 0.7, 0.95):
            for source_weight in (0.0, 0.5, 2.0):
                for limit in (1, 3, 7):
                    config = RetrievalConfig(mmr_lambda=lam, source_diversity_weight=source_weight)
                    got_scores, got_items = MemoryRetriever(config)._mmr_select(dict(scores), dict(items), limit)
                    expected = _reference_mmr_select(lam, source_weight, scores, items, limit)
                    context = f"seed={seed} lam={lam} source_weight={source_weight} limit={limit}"
                    if len(scores) <= limit:
                        assert list(got_scores) == list(scores), context
                    else:
                        assert list(got_scores) == expected, context
                        assert list(got_items) == expected, context
                    assert all(got_scores[mid] == scores[mid] for mid in got_scores), context

    def test_selection_is_complete_when_every_candidate_is_penalised(self) -> None:
        """Pure diversity over identical, same-source content drives every MMR value below -1."""
        config = RetrievalConfig(mmr_lambda=0.0, source_diversity_weight=0.5)
        results = [_sourced_result("identical content", f"m{i}", "chat-1") for i in range(5)]
        scores = {r.id: 0.5 for r in results}

        selected_scores, _ = MemoryRetriever(config)._mmr_select(scores, {r.id: r for r in results}, 3)

        assert len(selected_scores) == 3

    def test_ties_go_to_the_candidate_listed_first(self) -> None:
        config = RetrievalConfig(mmr_lambda=0.5)
        results = [_sourced_result(f"topic{i}", f"m{i}", None) for i in range(4)]
        scores = {r.id: 0.5 for r in results}

        selected_scores, _ = MemoryRetriever(config)._mmr_select(scores, {r.id: r for r in results}, 2)

        assert list(selected_scores) == ["m0", "m1"]
