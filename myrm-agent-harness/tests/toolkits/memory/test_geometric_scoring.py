"""Tests for geometric mean scoring system."""

from datetime import UTC, datetime, timedelta

import pytest

from myrm_agent_harness.toolkits.memory.config import RetrievalConfig
from myrm_agent_harness.toolkits.memory.retriever import MemoryRetriever
from myrm_agent_harness.toolkits.memory.signals import (
    SignalCalculator,
    get_default_half_life,
    get_default_signal_weights,
)
from myrm_agent_harness.toolkits.memory.types import (
    EpisodicMemory,
    MemorySearchResult,
    MemoryType,
    ProceduralMemory,
    SemanticMemory,
)


class TestSignalCalculator:
    """Test individual signal calculations."""

    def test_recency_factor_fresh_memory(self) -> None:
        """Fresh memory should have recency close to 1.0."""
        mem = SemanticMemory(content="test", created_at=datetime.now(UTC))
        factor = SignalCalculator.recency_factor(mem, half_life_days=7.0)
        assert factor == pytest.approx(1.0, abs=0.01)

    def test_recency_factor_half_life(self) -> None:
        """Memory at half-life should have recency of 0.5."""
        mem = SemanticMemory(content="test", created_at=datetime.now(UTC) - timedelta(days=7))
        factor = SignalCalculator.recency_factor(mem, half_life_days=7.0)
        assert factor == pytest.approx(0.5, abs=0.01)

    def test_recency_factor_old_memory(self) -> None:
        """Old memory should have low recency."""
        mem = SemanticMemory(content="test", created_at=datetime.now(UTC) - timedelta(days=60))
        factor = SignalCalculator.recency_factor(mem, half_life_days=7.0)
        assert factor < 0.01

    def test_recency_factor_no_decay(self) -> None:
        """Zero half-life should disable decay."""
        mem = SemanticMemory(content="test", created_at=datetime.now(UTC) - timedelta(days=365))
        factor = SignalCalculator.recency_factor(mem, half_life_days=0.0)
        assert factor == 1.0

    def test_importance_factor(self) -> None:
        """Importance should be extracted directly."""
        mem = SemanticMemory(content="test", importance=0.8)
        factor = SignalCalculator.importance_factor(mem)
        assert factor == 0.8

    def test_importance_factor_default(self) -> None:
        """Missing importance should default to 0.5."""
        mem = ProceduralMemory(content="test", trigger="test", action="test")
        factor = SignalCalculator.importance_factor(mem)
        assert factor == 0.5

    def test_preference_factor(self) -> None:
        """Preference strength should be extracted."""
        mem = SemanticMemory(content="test", preference_type="explicit", preference_strength=0.9)
        factor = SignalCalculator.preference_factor(mem)
        assert factor == 0.9

    def test_preference_factor_default(self) -> None:
        """Missing preference should default to 0.0."""
        mem = EpisodicMemory(content="test")
        factor = SignalCalculator.preference_factor(mem)
        assert factor == 0.0

    def test_confidence_factor(self) -> None:
        """Confidence should be extracted directly."""
        mem = SemanticMemory(content="test", confidence=0.85)
        factor = SignalCalculator.confidence_factor(mem)
        assert factor == 0.85

    def test_confidence_factor_default(self) -> None:
        """Missing confidence should default to 1.0."""
        mem = EpisodicMemory(content="test")
        factor = SignalCalculator.confidence_factor(mem)
        assert factor == 1.0

    def test_recency_factor_no_created_at_field(self) -> None:
        """Memory without created_at should return 1.0."""
        mem = ProceduralMemory(content="test", trigger="test", action="test")
        delattr(mem, "created_at")
        factor = SignalCalculator.recency_factor(mem, half_life_days=7.0)
        assert factor == 1.0

    def test_recency_factor_future_date(self) -> None:
        """Future created_at should return 1.0."""
        mem = SemanticMemory(content="test", created_at=datetime.now(UTC) + timedelta(days=10))
        factor = SignalCalculator.recency_factor(mem, half_life_days=7.0)
        assert factor == 1.0


class TestGeometricScoring:
    """Test weighted geometric mean scoring."""

    def test_semantic_dominance(self) -> None:
        """High semantic score should dominate even with low context signals."""
        config = RetrievalConfig(min_relevance_score=0.0)
        retriever = MemoryRetriever(config)

        high_semantic = SemanticMemory(
            content="high semantic", created_at=datetime.now(UTC) - timedelta(days=60), access_count=1, importance=0.3
        )

        low_semantic = SemanticMemory(
            content="low semantic", created_at=datetime.now(UTC), access_count=50, importance=1.0
        )

        result_high = MemorySearchResult(memory=high_semantic, score=0.9, memory_type=MemoryType.SEMANTIC)
        result_low = MemorySearchResult(memory=low_semantic, score=0.3, memory_type=MemoryType.SEMANTIC)

        score_high = retriever._boost(0.9, result_high, frozenset())
        score_low = retriever._boost(0.3, result_low, frozenset())

        assert score_high > score_low

    def test_recent_important_memory_outranks_an_older_slightly_more_relevant_one(self) -> None:
        """Recency and importance can outweigh a small relevance gap."""
        config = RetrievalConfig(min_relevance_score=0.0)
        retriever = MemoryRetriever(config)

        recent = SemanticMemory(content="recent", created_at=datetime.now(UTC) - timedelta(days=1), importance=0.7)
        old = SemanticMemory(content="old", created_at=datetime.now(UTC) - timedelta(days=60), importance=0.5)

        result_recent = MemorySearchResult(memory=recent, score=0.7, memory_type=MemoryType.SEMANTIC)
        result_old = MemorySearchResult(memory=old, score=0.75, memory_type=MemoryType.SEMANTIC)

        score_recent = retriever._boost(0.7, result_recent, frozenset())
        score_old = retriever._boost(0.75, result_old, frozenset())

        assert score_recent > score_old

    def test_profile_no_decay(self) -> None:
        """Profile memories should not decay over time."""
        config = RetrievalConfig(min_relevance_score=0.0)
        retriever = MemoryRetriever(config)

        old_profile = SemanticMemory(
            content="old preference",
            created_at=datetime.now(UTC) - timedelta(days=365),
            access_count=0,
            importance=0.5,
            preference_type="explicit",
            preference_strength=0.9,
        )

        result = MemorySearchResult(memory=old_profile, score=0.8, memory_type=MemoryType.PROFILE)

        score = retriever._boost(0.8, result, frozenset())
        assert score > 0.5

    def test_episodic_fast_decay(self) -> None:
        """Episodic memories should decay faster than semantic."""
        config = RetrievalConfig(min_relevance_score=0.0)
        retriever = MemoryRetriever(config)

        old_episodic = EpisodicMemory(
            content="old conversation",
            created_at=datetime.now(UTC) - timedelta(days=30),
            access_count=1,
            importance=0.5,
        )

        old_semantic = SemanticMemory(
            content="old knowledge", created_at=datetime.now(UTC) - timedelta(days=30), access_count=1, importance=0.5
        )

        result_epi = MemorySearchResult(memory=old_episodic, score=0.8, memory_type=MemoryType.EPISODIC)
        result_sem = MemorySearchResult(memory=old_semantic, score=0.8, memory_type=MemoryType.SEMANTIC)

        score_epi = retriever._boost(0.8, result_epi, frozenset())
        score_sem = retriever._boost(0.8, result_sem, frozenset())

        assert score_epi < score_sem

    def test_zero_semantic_score(self) -> None:
        """Zero semantic score should always result in zero final score."""
        config = RetrievalConfig(min_relevance_score=0.0)
        retriever = MemoryRetriever(config)

        mem = SemanticMemory(content="test", created_at=datetime.now(UTC), access_count=50, importance=1.0)

        result = MemorySearchResult(memory=mem, score=0.0, memory_type=MemoryType.SEMANTIC)

        score = retriever._boost(0.0, result, frozenset())
        assert score == 0.0

    def test_confidence_multiplier(self) -> None:
        """Confidence should multiply the final score."""
        config = RetrievalConfig(min_relevance_score=0.0)
        retriever = MemoryRetriever(config)

        high_conf = SemanticMemory(content="high confidence", confidence=1.0, importance=0.5)

        low_conf = SemanticMemory(content="low confidence", confidence=0.5, importance=0.5)

        result_high = MemorySearchResult(memory=high_conf, score=0.8, memory_type=MemoryType.SEMANTIC)
        result_low = MemorySearchResult(memory=low_conf, score=0.8, memory_type=MemoryType.SEMANTIC)

        score_high = retriever._boost(0.8, result_high, frozenset())
        score_low = retriever._boost(0.8, result_low, frozenset())

        assert score_high > score_low
        assert score_low == pytest.approx(score_high * 0.5, rel=0.1)

    def test_procedural_memory_scoring(self) -> None:
        """Procedural memory should use correct weights."""
        config = RetrievalConfig(min_relevance_score=0.0)
        retriever = MemoryRetriever(config)

        proc_mem = ProceduralMemory(
            content="test rule",
            trigger="when X",
            action="do Y",
            created_at=datetime.now(UTC) - timedelta(days=365),
            access_count=20,
            priority=1,
        )

        result = MemorySearchResult(memory=proc_mem, score=0.8, memory_type=MemoryType.PROCEDURAL)

        score = retriever._boost(0.8, result, frozenset())
        assert score > 0.0

    def test_geometric_score_with_zero_weight_signal(self) -> None:
        """Signals with zero weight should not affect score."""
        config = RetrievalConfig(min_relevance_score=0.0)
        retriever = MemoryRetriever(config)

        mem_with_pref = SemanticMemory(
            content="test", importance=0.5, preference_type="explicit", preference_strength=0.9
        )

        mem_without_pref = SemanticMemory(content="test", importance=0.5)

        result_with = MemorySearchResult(memory=mem_with_pref, score=0.8, memory_type=MemoryType.SEMANTIC)
        result_without = MemorySearchResult(memory=mem_without_pref, score=0.8, memory_type=MemoryType.SEMANTIC)

        score_with = retriever._boost(0.8, result_with, frozenset())
        score_without = retriever._boost(0.8, result_without, frozenset())

        assert score_with == pytest.approx(score_without)


class TestSignalWeights:
    """Test signal weight configurations."""

    def test_weights_sum_to_one(self) -> None:
        """All type weights should sum to 1.0."""
        for mem_type in MemoryType:
            weights = get_default_signal_weights(mem_type)
            total = sum(weights.values())
            assert total == pytest.approx(1.0, abs=0.001)

    def test_profile_no_time_decay(self) -> None:
        """Profile should have zero recency weight."""
        weights = get_default_signal_weights(MemoryType.PROFILE)
        assert weights["recency"] == 0.0

    def test_episodic_high_recency(self) -> None:
        """Episodic should have high recency weight."""
        weights = get_default_signal_weights(MemoryType.EPISODIC)
        assert weights["recency"] >= 0.2

    def test_semantic_balanced(self) -> None:
        """Semantic should have balanced weights with semantic dominant."""
        weights = get_default_signal_weights(MemoryType.SEMANTIC)
        assert weights["semantic"] > 0.5
        assert weights["recency"] > 0
        assert weights["type_prior"] > 0

    def test_half_life_by_type(self) -> None:
        """Different types should have appropriate half-lives."""
        assert get_default_half_life(MemoryType.PROFILE) == 0.0
        assert get_default_half_life(MemoryType.EPISODIC) == 7.0
        assert get_default_half_life(MemoryType.SEMANTIC) == 30.0
        assert get_default_half_life(MemoryType.PROCEDURAL) == 0.0

    def test_signal_weights_fallback(self) -> None:
        """Unknown memory type should fallback to SEMANTIC weights."""
        from myrm_agent_harness.toolkits.memory.signals import get_default_signal_weights

        class FakeMemoryType:
            def upper(self):
                return "UNKNOWN_TYPE"

        weights = get_default_signal_weights(FakeMemoryType())
        semantic_weights = get_default_signal_weights(MemoryType.SEMANTIC)
        assert weights == semantic_weights

    def test_half_life_fallback(self) -> None:
        """Unknown memory type should fallback to 30.0 days."""
        from myrm_agent_harness.toolkits.memory.signals import get_default_half_life

        class FakeMemoryType:
            def upper(self):
                return "UNKNOWN_TYPE"

        half_life = get_default_half_life(FakeMemoryType())
        assert half_life == 30.0


class TestEndToEndScoring:
    """Test complete scoring pipeline."""

    def test_ranking_with_geometric_scoring(self) -> None:
        """Test that ranking works correctly with geometric scoring."""
        config = RetrievalConfig(min_relevance_score=0.0)
        retriever = MemoryRetriever(config)

        memories = [
            MemorySearchResult(
                memory=SemanticMemory(
                    content="recent", created_at=datetime.now(UTC) - timedelta(days=2), importance=0.7
                ),
                score=0.7,
                memory_type=MemoryType.SEMANTIC,
            ),
            MemorySearchResult(
                memory=SemanticMemory(content="old", created_at=datetime.now(UTC) - timedelta(days=60), importance=0.5),
                score=0.75,
                memory_type=MemoryType.SEMANTIC,
            ),
            MemorySearchResult(
                memory=SemanticMemory(
                    content="very relevant", created_at=datetime.now(UTC) - timedelta(days=30), importance=0.8
                ),
                score=0.95,
                memory_type=MemoryType.SEMANTIC,
            ),
        ]

        ranked = retriever.rank(memories, limit=3)

        assert len(ranked) == 3
        assert ranked[0].content == "very relevant"
        assert ranked[1].content == "recent"
        assert ranked[2].content == "old"

    def test_correction_chain_suppression_still_works(self) -> None:
        """Correction chain suppression should work with geometric scoring."""
        config = RetrievalConfig(min_relevance_score=0.0)
        retriever = MemoryRetriever(config)

        old_mem = SemanticMemory(id="old-id", content="old fact", importance=0.8)

        corrected_mem = SemanticMemory(id="new-id", content="corrected fact", correction_of="old-id", importance=0.9)

        results = [
            MemorySearchResult(memory=old_mem, score=0.9, memory_type=MemoryType.SEMANTIC),
            MemorySearchResult(memory=corrected_mem, score=0.85, memory_type=MemoryType.SEMANTIC),
        ]

        ranked = retriever.rank(results, limit=2)

        assert ranked[0].id == "new-id"
        assert ranked[1].id == "old-id"
        assert ranked[0].score > ranked[1].score


class TestPerformance:
    """Test performance characteristics."""

    def test_scoring_is_fast(self) -> None:
        """Geometric scoring should complete in reasonable time."""
        import time

        config = RetrievalConfig(min_relevance_score=0.0)
        retriever = MemoryRetriever(config)

        memories = [
            MemorySearchResult(
                memory=SemanticMemory(
                    content=f"memory {i}",
                    created_at=datetime.now(UTC) - timedelta(days=i % 60),
                    access_count=i % 50,
                    importance=0.5 + (i % 5) * 0.1,
                ),
                score=0.5 + (i % 50) * 0.01,
                memory_type=MemoryType.SEMANTIC,
            )
            for i in range(100)
        ]

        start = time.perf_counter()
        ranked = retriever.rank(memories, limit=10)
        elapsed = time.perf_counter() - start

        assert len(ranked) == 10
        assert elapsed < 0.2
