"""Recall counts never move a memory in the ranking.

Every hit a search returns is stamped (``access_count``) whether or not the agent used it, so the
count measures exposure, not usefulness. Feeding it back into the ranking would keep showing whatever
was shown first. The stamp serves lifecycle only (forgetting, staleness review, health, the memory card);
ranking comes from relevance, recency, importance, the user's rating and a fixed per-type prior.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from myrm_agent_harness.toolkits.memory.config import RetrievalConfig
from myrm_agent_harness.toolkits.memory.retriever import MemoryRetriever
from myrm_agent_harness.toolkits.memory.signals import get_default_signal_weights
from myrm_agent_harness.toolkits.memory.types import (
    ClaimMemory,
    EpisodicMemory,
    MemorySearchResult,
    MemoryType,
    ProceduralMemory,
    SemanticMemory,
)

_ALL_TYPES = [
    MemoryType.PROFILE,
    MemoryType.SEMANTIC,
    MemoryType.CLAIM,
    MemoryType.EPISODIC,
    MemoryType.PROCEDURAL,
]
_USAGE_LEVELS = (0, 5, 500)


def _retriever() -> MemoryRetriever:
    return MemoryRetriever(RetrievalConfig(min_relevance_score=0.0))


def _memory(
    memory_type: MemoryType, access_count: int, *, age_days: int = 10
) -> SemanticMemory | EpisodicMemory | ProceduralMemory | ClaimMemory:
    created_at = datetime.now(UTC) - timedelta(days=age_days)
    if memory_type is MemoryType.EPISODIC:
        return EpisodicMemory(content="note", created_at=created_at, access_count=access_count)
    if memory_type is MemoryType.PROCEDURAL:
        return ProceduralMemory(
            content="rule", trigger="when X", action="do Y", created_at=created_at, access_count=access_count
        )
    if memory_type is MemoryType.CLAIM:
        return ClaimMemory(
            content="claim",
            claim_key="k",
            title="t",
            claim_text="claim",
            created_at=created_at,
            access_count=access_count,
        )
    return SemanticMemory(content="fact", created_at=created_at, access_count=access_count)


def _hit(memory_type: MemoryType, access_count: int, score: float) -> MemorySearchResult:
    return MemorySearchResult(memory=_memory(memory_type, access_count), score=score, memory_type=memory_type)


@pytest.mark.parametrize("memory_type", _ALL_TYPES)
def test_score_does_not_depend_on_how_often_a_memory_was_recalled(memory_type: MemoryType) -> None:
    retriever = _retriever()

    scores = [retriever._geometric_score(0.7, _hit(memory_type, count, 0.7)) for count in _USAGE_LEVELS]

    assert scores[0] > 0.0
    assert scores == [scores[0]] * len(_USAGE_LEVELS)


@pytest.mark.parametrize(("memory_type", "worn_relevance"), [(MemoryType.SEMANTIC, 0.60), (MemoryType.EPISODIC, 0.40)])
def test_a_more_relevant_memory_outranks_a_heavily_recalled_one(memory_type: MemoryType, worn_relevance: float) -> None:
    relevant = _hit(memory_type, 0, 0.80)
    worn = _hit(memory_type, 500, worn_relevance)

    ranked = _retriever().rank([worn, relevant], limit=2)

    assert [r.id for r in ranked] == [relevant.id, worn.id]


@pytest.mark.parametrize(
    ("memory_type", "discount"),
    [(MemoryType.SEMANTIC, 0.01**0.05), (MemoryType.EPISODIC, 0.01**0.12), (MemoryType.PROFILE, 1.0)],
)
def test_a_memory_that_is_perfect_on_every_signal_keeps_only_its_fixed_type_discount(
    memory_type: MemoryType, discount: float
) -> None:
    perfect = SemanticMemory(content="fact", importance=1.0, user_rating=1.0, preference_strength=1.0)
    if memory_type is MemoryType.EPISODIC:
        perfect = EpisodicMemory(content="note", importance=1.0, user_rating=1.0)
    result = MemorySearchResult(memory=perfect, score=1.0, memory_type=memory_type)

    assert _retriever()._geometric_score(1.0, result) == pytest.approx(discount)


def test_the_type_prior_replaces_the_usage_weight() -> None:
    expected = {
        MemoryType.PROFILE: 0.0,
        MemoryType.SEMANTIC: 0.05,
        MemoryType.CLAIM: 0.05,
        MemoryType.EPISODIC: 0.12,
        MemoryType.PROCEDURAL: 0.12,
    }
    for memory_type, prior in expected.items():
        weights = get_default_signal_weights(memory_type)
        assert "frequency" not in weights
        assert weights["type_prior"] == prior
