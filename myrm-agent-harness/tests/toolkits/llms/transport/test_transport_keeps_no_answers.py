"""The transport keeps no answers: a request that was answered once is put to the provider again.

A stored answer would stand in for a key the provider has since revoked, for an endpoint that has gone away and for the
latency a settings probe measures. A caller that wants a recorded answer asks for one explicitly (``memo_run``, the
embedding cache). Every call below is issued twice, unchanged, against a provider double that counts its requests.
"""

from __future__ import annotations

import asyncio

import httpx
import pytest

from myrm_agent_harness.toolkits.llms.transport import embeddings, rerank
from myrm_agent_harness.toolkits.llms.transport.client import get_transport

from .gateway_bodies import Body, answer, chunk
from .provider_double import BASE, Provider, adrain, drain, json_response, sse_response

_RESPONSE: Body = {
    "id": "resp_1",
    "object": "response",
    "status": "completed",
    "output": [{"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "hello"}]}],
    "usage": {"input_tokens": 3, "output_tokens": 2, "total_tokens": 5},
}


def _chat(**changes: object) -> dict[str, object]:
    return {
        "model": "openai/gpt-4o-mini",
        "api_base": BASE,
        "api_key": "k",
        "temperature": 0.0,
        "messages": [{"role": "user", "content": "hi"}],
        **changes,
    }


def _responses(**changes: object) -> dict[str, object]:
    return {"model": "openai/gpt-4o-mini", "api_base": BASE, "api_key": "k", "input": "hi", **changes}


def _chat_stream() -> httpx.Response:
    return sse_response(
        chunk({"role": "assistant", "content": "hel"}),
        chunk({"content": "lo"}),
        chunk({}, finish="stop"),
        {"id": "c1", "choices": [], "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5}},
    )


def _responses_stream() -> httpx.Response:
    return sse_response(
        {"type": "response.created", "response": {"id": "resp_1", "status": "in_progress"}},
        {"type": "response.output_text.delta", "delta": "hello"},
        {"type": "response.completed", "response": _RESPONSE},
    )


class TestChat:
    def test_an_identical_request_reaches_the_provider_each_time(self, provider: Provider) -> None:
        provider.serves(json_response(answer()))

        get_transport().completion(**_chat())
        get_transport().completion(**_chat())

        assert len(provider.requests) == 2

    def test_the_async_path_asks_again_too(self, provider: Provider) -> None:
        provider.serves(json_response(answer()))

        async def ask_twice() -> None:
            await get_transport().acompletion(**_chat())
            await get_transport().acompletion(**_chat())

        asyncio.run(ask_twice())

        assert len(provider.requests) == 2

    def test_an_identical_stream_is_read_from_the_provider_each_time(self, provider: Provider) -> None:
        provider.serves(_chat_stream())

        drain(get_transport().completion(**_chat(stream=True)))
        drain(get_transport().completion(**_chat(stream=True)))

        assert len(provider.requests) == 2

    def test_the_async_stream_is_read_from_the_provider_each_time(self, provider: Provider) -> None:
        provider.serves(_chat_stream())

        async def read_twice() -> None:
            await adrain(await get_transport().acompletion(**_chat(stream=True)))
            await adrain(await get_transport().acompletion(**_chat(stream=True)))

        asyncio.run(read_twice())

        assert len(provider.requests) == 2

    def test_a_provider_that_has_since_refused_the_request_is_heard(self, provider: Provider) -> None:
        provider.serves(json_response(answer()))
        get_transport().completion(**_chat())

        provider.serves(httpx.Response(401, json={"error": {"message": "Incorrect API key provided"}}))
        with pytest.raises(Exception, match="Incorrect API key provided"):
            get_transport().completion(**_chat())


class TestResponses:
    def test_an_identical_request_reaches_the_provider_each_time(self, provider: Provider) -> None:
        provider.serves(json_response(_RESPONSE))

        get_transport().responses(**_responses())
        get_transport().responses(**_responses())

        assert len(provider.requests) == 2

    def test_the_async_path_asks_again_too(self, provider: Provider) -> None:
        provider.serves(json_response(_RESPONSE))

        async def ask_twice() -> None:
            await get_transport().aresponses(**_responses())
            await get_transport().aresponses(**_responses())

        asyncio.run(ask_twice())

        assert len(provider.requests) == 2

    def test_an_identical_event_stream_is_read_from_the_provider_each_time(self, provider: Provider) -> None:
        provider.serves(_responses_stream())

        drain(get_transport().responses(**_responses(stream=True)))
        drain(get_transport().responses(**_responses(stream=True)))

        assert len(provider.requests) == 2

    def test_the_async_event_stream_is_read_from_the_provider_each_time(self, provider: Provider) -> None:
        provider.serves(_responses_stream())

        async def read_twice() -> None:
            await adrain(await get_transport().aresponses(**_responses(stream=True)))
            await adrain(await get_transport().aresponses(**_responses(stream=True)))

        asyncio.run(read_twice())

        assert len(provider.requests) == 2


class TestEmbeddingsAndRerank:
    def test_the_same_texts_are_embedded_by_the_provider_each_time(self, provider: Provider) -> None:
        provider.serves(json_response({"data": [{"index": 0, "embedding": [0.5, 0.25]}]}))

        async def embed() -> list[list[float]]:
            return await embeddings.aembed("openai/text-embedding-3-small", ["a"], api_key="k", api_base=BASE)

        first = asyncio.run(embed())
        second = asyncio.run(embed())

        assert (first, second, len(provider.requests)) == ([[0.5, 0.25]], [[0.5, 0.25]], 2)

    def test_the_same_ranking_is_asked_of_the_provider_each_time(self, provider: Provider) -> None:
        provider.serves(
            json_response({"results": [{"index": 1, "relevance_score": 0.9}, {"index": 0, "relevance_score": 0.1}]})
        )

        async def score() -> list[tuple[int, float]]:
            return await rerank.arerank("cohere/rerank-v3.5", "q", ["a", "b"], top_n=2, api_key="k", api_base=BASE)

        first = asyncio.run(score())
        second = asyncio.run(score())

        assert (first, second, len(provider.requests)) == ([(1, 0.9), (0, 0.1)], [(1, 0.9), (0, 0.1)], 2)
