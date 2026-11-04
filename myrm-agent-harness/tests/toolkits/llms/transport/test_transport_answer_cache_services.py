"""The answer cache on the Responses, embedding and rerank calls, against a provider double that counts its requests."""

from __future__ import annotations

import asyncio

import httpx
import pytest

from myrm_agent_harness.toolkits.llms.transport import embeddings, rerank
from myrm_agent_harness.toolkits.llms.transport.client import get_transport

from .gateway_bodies import Body
from .provider_double import BASE, Provider, adrain, drain, json_response, sse_response

pytestmark = pytest.mark.usefixtures("cache_on")

_RESPONSE: Body = {
    "id": "resp_1",
    "object": "response",
    "status": "completed",
    "output": [{"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "hello"}]}],
    "usage": {"input_tokens": 3, "output_tokens": 2, "total_tokens": 5},
}


def _params(**changes: object) -> dict[str, object]:
    return {"model": "openai/gpt-4o-mini", "api_base": BASE, "api_key": "k", "input": "hi", **changes}


def _response_events(*, terminal: str = "response.completed") -> httpx.Response:
    return sse_response(
        {"type": "response.created", "response": {"id": "resp_1", "status": "in_progress"}},
        {"type": "response.output_text.delta", "delta": "hello"},
        {"type": terminal, "response": _RESPONSE},
    )


class TestResponsesWire:
    def test_an_identical_responses_request_reaches_the_provider_once(self, provider: Provider) -> None:
        provider.serves(json_response(_RESPONSE))

        first = get_transport().responses(**_params())
        second = get_transport().responses(**_params())

        assert (first, second, len(provider.requests)) == (_RESPONSE, _RESPONSE, 1)

    def test_a_failed_response_is_asked_again(self, provider: Provider) -> None:
        provider.serves(json_response({**_RESPONSE, "status": "failed"}))

        get_transport().responses(**_params())
        get_transport().responses(**_params())

        assert len(provider.requests) == 2

    def test_an_async_failed_response_is_asked_again(self, provider: Provider) -> None:
        provider.serves(json_response({**_RESPONSE, "status": "failed"}))

        async def ask_twice() -> None:
            await get_transport().aresponses(**_params())
            await get_transport().aresponses(**_params())

        asyncio.run(ask_twice())

        assert len(provider.requests) == 2

    def test_a_completed_event_stream_is_replayed(self, provider: Provider) -> None:
        provider.serves(_response_events())

        live = drain(get_transport().responses(**_params(stream=True)))
        replayed = drain(get_transport().responses(**_params(stream=True)))

        assert (replayed, len(provider.requests)) == (live, 1)

    def test_an_event_stream_that_did_not_complete_is_asked_again(self, provider: Provider) -> None:
        provider.serves(_response_events(terminal="response.incomplete"))

        drain(get_transport().responses(**_params(stream=True)))
        drain(get_transport().responses(**_params(stream=True)))

        assert len(provider.requests) == 2

    def test_the_async_twin_replays_a_completed_event_stream(self, provider: Provider) -> None:
        provider.serves(_response_events())

        async def run() -> tuple[list[object], list[object]]:
            live = await adrain(await get_transport().aresponses(**_params(stream=True)))
            replayed = await adrain(await get_transport().aresponses(**_params(stream=True)))
            return live, replayed

        live, replayed = asyncio.run(run())

        assert (replayed, len(provider.requests)) == (live, 1)


class TestEmbeddingsAndRerank:
    def test_the_same_texts_are_embedded_once(self, provider: Provider) -> None:
        provider.serves(
            json_response({"data": [{"index": 0, "embedding": [0.5, 0.25]}, {"index": 1, "embedding": [1.0, 2.0]}]})
        )

        async def embed(texts: list[str]) -> list[list[float]]:
            return await embeddings.aembed("openai/text-embedding-3-small", texts, api_key="k", api_base=BASE)

        first = asyncio.run(embed(["a", "b"]))
        second = asyncio.run(embed(["a", "b"]))
        asyncio.run(embed(["a", "c"]))

        assert (first, second, len(provider.requests)) == ([[0.5, 0.25], [1.0, 2.0]], [[0.5, 0.25], [1.0, 2.0]], 2)

    def test_the_same_ranking_is_asked_once_and_keeps_its_pairs(self, provider: Provider) -> None:
        provider.serves(
            json_response({"results": [{"index": 1, "relevance_score": 0.9}, {"index": 0, "relevance_score": 0.1}]})
        )

        async def score() -> list[tuple[int, float]]:
            return await rerank.arerank("cohere/rerank-v3.5", "q", ["a", "b"], top_n=2, api_key="k", api_base=BASE)

        first = asyncio.run(score())
        second = asyncio.run(score())

        assert (first, second, len(provider.requests)) == ([(1, 0.9), (0, 0.1)], [(1, 0.9), (0, 0.1)], 1)
