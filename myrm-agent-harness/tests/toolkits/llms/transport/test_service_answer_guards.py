"""Embedding and rerank answers that do not look like the provider's contract fail loudly instead of corrupting a store."""

from __future__ import annotations

from collections.abc import Callable, Iterator

import pytest

from myrm_agent_harness.toolkits.llms.transport import embeddings, rerank
from myrm_agent_harness.toolkits.llms.transport.http import PreparedRequest

Answer = dict[str, object]


@pytest.fixture
def answer(monkeypatch: pytest.MonkeyPatch) -> Iterator[Callable[[Answer], None]]:
    """``answer(payload)`` makes every embedding and rerank call return ``payload``."""
    box: list[Answer] = [{}]

    async def fake_send(request: PreparedRequest) -> Answer:
        return box[0]

    monkeypatch.setattr(embeddings, "asend_json", fake_send)
    monkeypatch.setattr(rerank, "asend_json", fake_send)

    def arm(payload: Answer) -> None:
        box[0] = payload

    yield arm


class TestEmbeddingAnswers:
    @pytest.mark.parametrize(
        ("model", "payload", "message"),
        [
            ("openai/text-embedding-3-small", {"data": [{"index": 0, "embedding": "oops"}]}, "malformed vector"),
            ("openai/text-embedding-3-small", {"data": "oops"}, "no vectors for 1 inputs"),
            ("cohere/embed-v4.0", {"embeddings": "oops"}, "Cohere returned a malformed embeddings payload"),
            ("gemini/text-embedding-004", {"embeddings": None}, "Gemini returned a malformed embeddings payload"),
            ("gemini/text-embedding-004", {"embeddings": [5]}, "malformed vector"),
        ],
        ids=["openai-vector", "openai-data", "cohere", "gemini-list", "gemini-entry"],
    )
    async def test_a_malformed_answer_is_an_error_naming_the_problem(
        self, answer: Callable[[Answer], None], model: str, payload: Answer, message: str
    ) -> None:
        answer(payload)

        with pytest.raises(ValueError, match=message):
            await embeddings.aembed(model, ["text"], api_key="k")

    async def test_cohere_may_answer_with_a_bare_list_of_vectors(self, answer: Callable[[Answer], None]) -> None:
        answer({"embeddings": [[0.5, 1]]})

        assert await embeddings.aembed("cohere/embed-v4.0", ["text"], api_key="k") == [[0.5, 1.0]]


class TestRerankAnswers:
    @pytest.mark.parametrize(
        ("payload", "message"),
        [
            ({"results": "oops"}, "answered without a result list"),
            ({"results": ["oops"]}, "malformed result entry"),
            ({"results": [{"index": -1, "relevance_score": 0.5}]}, "does not match the documents"),
            ({"results": [{"index": 0, "relevance_score": "high"}]}, "does not match the documents"),
            ({"results": [{"relevance_score": 0.5}]}, "does not match the documents"),
        ],
        ids=["no-list", "entry-not-a-mapping", "negative-index", "score-not-a-number", "missing-index"],
    )
    async def test_a_malformed_answer_is_an_error_naming_the_problem(
        self, answer: Callable[[Answer], None], payload: Answer, message: str
    ) -> None:
        answer(payload)

        with pytest.raises(ValueError, match=message):
            await rerank.arerank("cohere/rerank-v3.5", "q", ["a", "b"], top_n=2, api_key="k")
