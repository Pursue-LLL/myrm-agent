"""Cloud reranker: what it asks the transport for, how it maps the answer back, and how it fails."""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass

import pytest

from myrm_agent_harness.toolkits.retriever.reranker import cloud_reranker, factory
from myrm_agent_harness.toolkits.retriever.reranker.base import RerankResult
from myrm_agent_harness.toolkits.retriever.reranker.cloud_reranker import CloudReranker
from myrm_agent_harness.toolkits.retriever.reranker.factory import RerankerConfig, get_reranker_service

Scorer = Callable[[str, Sequence[str]], list[tuple[int, float]]]


@dataclass(frozen=True)
class Call:
    model: str
    query: str
    documents: list[str]
    top_n: int
    api_key: str | None
    api_base: str | None


@pytest.fixture
def transport(monkeypatch: pytest.MonkeyPatch) -> tuple[list[Call], list[Scorer]]:
    """Replace the network call; the scorer in ``scorers[0]`` decides each answer (indexes into the documents sent)."""
    calls: list[Call] = []
    scorers: list[Scorer] = [lambda query, documents: [(i, 1.0 / (i + 1)) for i in range(len(documents))]]

    async def fake_arerank(
        model: str,
        query: str,
        documents: Sequence[str],
        *,
        top_n: int,
        api_key: str | None = None,
        api_base: str | None = None,
    ) -> list[tuple[int, float]]:
        calls.append(Call(model, query, list(documents), top_n, api_key, api_base))
        return scorers[0](query, documents)

    monkeypatch.setattr(cloud_reranker, "arerank", fake_arerank)
    return calls, scorers


def _reranker() -> CloudReranker:
    return CloudReranker(model="cohere/rerank-v3.5", api_key="key", api_base="https://gw.example/v1")


class TestRerank:
    async def test_hits_come_back_as_the_provider_ranked_them_with_their_document_text(
        self, transport: tuple[list[Call], list[Scorer]]
    ) -> None:
        calls, scorers = transport
        scorers[0] = lambda query, documents: [(2, 0.9), (1, 0.5), (0, 0.2)]

        results = await _reranker().rerank("q", ["a", "b", "c"])

        assert results == [
            RerankResult(index=2, score=0.9, text="c"),
            RerankResult(index=1, score=0.5, text="b"),
            RerankResult(index=0, score=0.2, text="a"),
        ]
        assert calls == [Call("cohere/rerank-v3.5", "q", ["a", "b", "c"], 3, "key", "https://gw.example/v1")]

    async def test_top_k_is_the_limit_asked_of_the_provider_and_its_answer_is_passed_on(
        self, transport: tuple[list[Call], list[Scorer]]
    ) -> None:
        calls, scorers = transport
        scorers[0] = lambda query, documents: [(0, 0.2), (2, 0.9), (1, 0.5)]  # a provider may ignore top_n

        results = await _reranker().rerank("q", ["a", "b", "c"], top_k=2)

        assert calls[0].top_n == 2
        assert [r.index for r in results] == [0, 2, 1]

    async def test_no_documents_means_no_call(self, transport: tuple[list[Call], list[Scorer]]) -> None:
        calls, _ = transport

        assert await _reranker().rerank("q", []) == []
        assert calls == []

    async def test_an_empty_answer_is_a_warning_and_no_results(
        self, transport: tuple[list[Call], list[Scorer]], caplog: pytest.LogCaptureFixture
    ) -> None:
        _, scorers = transport
        scorers[0] = lambda query, documents: []

        with caplog.at_level(logging.WARNING):
            assert await _reranker().rerank("q", ["a"]) == []

        assert "no results" in caplog.text

    async def test_a_failed_call_is_logged_and_raised_not_swallowed(
        self, transport: tuple[list[Call], list[Scorer]], caplog: pytest.LogCaptureFixture
    ) -> None:
        _, scorers = transport

        def refuse(query: str, documents: Sequence[str]) -> list[tuple[int, float]]:
            raise ValueError("rerank answered without a result list")

        scorers[0] = refuse

        with caplog.at_level(logging.WARNING), pytest.raises(ValueError, match="without a result list"):
            await _reranker().rerank("q", ["a"])

        assert "Rerank call failed" in caplog.text


class TestRerankPairs:
    async def test_no_pairs_means_no_scores_and_no_call(self, transport: tuple[list[Call], list[Scorer]]) -> None:
        calls, _ = transport

        assert await _reranker().rerank_pairs([]) == []
        assert calls == []

    async def test_pairs_of_one_query_share_a_call_and_scores_land_on_the_original_positions(
        self, transport: tuple[list[Call], list[Scorer]]
    ) -> None:
        calls, scorers = transport
        # q1 sees [d0, d2], q2 sees [d1]; the provider scores each document by its own length so positions are checkable.
        scorers[0] = lambda query, documents: [(i, float(len(doc))) for i, doc in enumerate(documents)]
        pairs = [("q1", "d0"), ("q2", "d1-longer"), ("q1", "d2-even-longer")]

        scores = await _reranker().rerank_pairs(pairs)

        assert scores == [2.0, 9.0, 14.0]
        assert sorted((c.query, c.documents, c.top_n) for c in calls) == [
            ("q1", ["d0", "d2-even-longer"], 2),
            ("q2", ["d1-longer"], 1),
        ]

    async def test_one_failing_query_fails_the_batch_instead_of_returning_zero_scores(
        self, transport: tuple[list[Call], list[Scorer]]
    ) -> None:
        _, scorers = transport

        def refuse(query: str, documents: Sequence[str]) -> list[tuple[int, float]]:
            if query == "bad":
                raise ValueError("boom")
            return [(0, 1.0)]

        scorers[0] = refuse

        with pytest.raises(ValueError, match="boom"):
            await _reranker().rerank_pairs([("good", "a"), ("bad", "b")])


class TestFactory:
    @pytest.fixture(autouse=True)
    def _fresh_cache(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(factory, "_cache", {})

    def test_the_same_configuration_shares_one_instance(self) -> None:
        config = RerankerConfig(model="cohere/rerank-v3.5", api_key="k")

        assert get_reranker_service(config) is get_reranker_service(
            RerankerConfig(model="cohere/rerank-v3.5", api_key="k")
        )

    @pytest.mark.parametrize(
        "other",
        [
            RerankerConfig(model="jina_ai/jina-reranker-v2-base-multilingual", api_key="k"),
            RerankerConfig(model="cohere/rerank-v3.5", api_key="other-key"),
            RerankerConfig(model="cohere/rerank-v3.5", api_key="k", api_base="https://gw.example/v1"),
        ],
        ids=["model", "key", "endpoint"],
    )
    def test_any_difference_in_model_key_or_endpoint_gets_its_own_instance(self, other: RerankerConfig) -> None:
        base = get_reranker_service(RerankerConfig(model="cohere/rerank-v3.5", api_key="k"))

        assert get_reranker_service(other) is not base
