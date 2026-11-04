"""The memory rerank gate over the real CloudReranker orders the head by what the provider scored.

test_rerank_gate.py scripts ``rerank_pairs`` itself, so it cannot see whether ``CloudReranker.rerank_pairs`` maps each
score back to the candidate it belongs to. Here only the network is replaced.
"""

from time import perf_counter

from myrm_agent_harness.toolkits.memory._internal.rerank_gate import apply_cross_rerank
from myrm_agent_harness.toolkits.memory.config import MemoryConfig
from myrm_agent_harness.toolkits.memory.types import MemorySearchResult, MemoryType, SemanticMemory
from tests.support.rerank_provider import Relevance, provider_reranker

QUERY = "when did we rotate the signing key"


def _candidate(memory_id: str, content: str, fused_score: float) -> MemorySearchResult:
    return MemorySearchResult(
        memory=SemanticMemory(id=memory_id, content=content, user_id="user"),
        score=fused_score,
        memory_type=MemoryType.SEMANTIC,
    )


async def test_head_is_ordered_by_provider_relevance() -> None:
    # Fused order a, b, c, d; the provider finds b most relevant, then d, a, c.
    contents = {
        "a": "quarterly budget notes",
        "b": "the signing key was rotated on the first of March",
        "c": "office seating chart",
        "d": "key management overview",
    }
    earned = dict(zip("abcd", (0.1, 0.9, 0.05, 0.5), strict=True))
    relevance: Relevance = {(QUERY, contents[key]): earned[key] for key in contents}
    results = [_candidate(key, contents[key], 0.9 - 0.1 * rank) for rank, key in enumerate("abcd")]

    async with provider_reranker(relevance) as reranker:
        outcome = await apply_cross_rerank(
            results,
            QUERY,
            reranker=reranker,
            config=MemoryConfig(embedding_model="test-model"),
            deadline=perf_counter() + 30.0,
        )

    assert outcome.applied
    assert not outcome.degraded
    assert [result.memory.id for result in outcome.results] == ["b", "d", "a", "c"]
