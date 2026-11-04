"""CloudReranker.rerank_pairs hands every pair the score its own document earned.

A provider answers with hits ranked by relevance, each labelled with the index of the document it scored. The score
must follow that label back to the pair; reading the hits in the order they arrive gives every document the score of
whichever document ranked at its position. The Web reranking pipeline is covered over the same provider because it is
the consumer that sorts each query's documents by these scores.
"""

from __future__ import annotations

import pytest
from langchain_core.documents import Document

from myrm_agent_harness.toolkits.retriever.hybrid_search.reranking_pipeline import RerankingPipeline
from myrm_agent_harness.toolkits.retriever.reranker.base import RerankResult
from myrm_agent_harness.toolkits.retriever.reranker.cloud_reranker import CloudReranker
from tests.support.rerank_provider import Relevance, provider_reranker

QUERY = "how do I rotate the signing key"
LOW = "release notes for the mobile app"
HIGH = "rotating the signing key takes three steps"
MID = "key management overview"
RELEVANCE: Relevance = {(QUERY, LOW): 0.1, (QUERY, HIGH): 0.9, (QUERY, MID): 0.5}


async def test_each_pair_gets_the_score_its_own_document_earned() -> None:
    pairs = [(QUERY, LOW), (QUERY, HIGH), (QUERY, MID)]
    async with provider_reranker(RELEVANCE) as reranker:
        scores = await reranker.rerank_pairs(pairs)
    assert scores == [0.1, 0.9, 0.5]


async def test_pairs_of_several_queries_keep_their_input_positions() -> None:
    first, second = "first question", "second question"
    relevance: Relevance = {
        (first, "a1"): 0.2,
        (first, "a2"): 0.8,
        (first, "a3"): 0.5,
        (second, "b1"): 0.7,
        (second, "b2"): 0.1,
    }
    pairs = [(first, "a1"), (second, "b1"), (first, "a2"), (second, "b2"), (first, "a3")]
    async with provider_reranker(relevance) as reranker:
        scores = await reranker.rerank_pairs(pairs)
    assert scores == [relevance[pair] for pair in pairs]


async def test_identical_documents_each_keep_their_own_slot() -> None:
    relevance: Relevance = {(QUERY, "same text"): 0.4, (QUERY, "other text"): 0.9}
    pairs = [(QUERY, "same text"), (QUERY, "other text"), (QUERY, "same text")]
    async with provider_reranker(relevance) as reranker:
        scores = await reranker.rerank_pairs(pairs)
    assert scores == [0.4, 0.9, 0.4]


async def test_a_document_the_provider_leaves_out_scores_zero() -> None:
    pairs = [(QUERY, LOW), (QUERY, HIGH), (QUERY, MID)]
    async with provider_reranker(RELEVANCE, omit=frozenset({HIGH})) as reranker:
        scores = await reranker.rerank_pairs(pairs)
    assert scores == [0.1, 0.0, 0.5]


async def test_no_pairs_score_to_an_empty_list() -> None:
    async with provider_reranker({}) as reranker:
        assert await reranker.rerank_pairs([]) == []


class _MislabelingReranker(CloudReranker):
    """A reranker whose provider labels its only hit with an index of its own choosing."""

    def __init__(self, index: int) -> None:
        super().__init__(model="openai/test-reranker", api_key="test-key")
        self._index = index

    async def rerank(self, query: str, documents: list[str], top_k: int | None = None) -> list[RerankResult]:
        return [RerankResult(index=self._index, score=0.9, text="")]


@pytest.mark.parametrize("index", [-1, 2])
async def test_a_hit_labelled_outside_the_queried_documents_is_an_error(index: int) -> None:
    reranker = _MislabelingReranker(index)
    with pytest.raises(ValueError, match="outside the 2 documents"):
        await reranker.rerank_pairs([(QUERY, LOW), (QUERY, HIGH)])


async def test_pipeline_sorts_each_query_by_what_the_provider_scored() -> None:
    first, second = "first question", "second question"
    relevance: Relevance = {
        (first, "a1"): 0.2,
        (first, "a2"): 0.8,
        (first, "a3"): 0.5,
        (second, "b1"): 0.1,
        (second, "b2"): 0.7,
    }
    query_results = {
        first: [(Document(page_content=text), 0.9 - 0.1 * rank) for rank, text in enumerate(("a1", "a2", "a3"))],
        second: [(Document(page_content=text), 0.9 - 0.1 * rank) for rank, text in enumerate(("b1", "b2"))],
    }
    async with provider_reranker(relevance) as reranker:
        reranked = await RerankingPipeline(reranker).rerank_query_results(query_results)
    assert [(doc.page_content, score) for doc, score in reranked[first]] == [("a2", 0.8), ("a3", 0.5), ("a1", 0.2)]
    assert [(doc.page_content, score) for doc, score in reranked[second]] == [("b2", 0.7), ("b1", 0.1)]
