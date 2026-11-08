"""Which calls the transport may repeat: model calls yes; embeddings, rerank and images own their retries elsewhere."""

from __future__ import annotations

from collections.abc import Callable, Mapping

import pytest

from myrm_agent_harness.toolkits.llms.errors.classifier import ErrorKind, classify_error
from myrm_agent_harness.toolkits.llms.transport import (
    anthropic_messages,
    embeddings,
    gemini_generate,
    images,
    ollama_chat,
    openai_chat,
    openai_responses,
    rerank,
)
from myrm_agent_harness.toolkits.llms.transport.errors import LLMResponseError
from myrm_agent_harness.toolkits.llms.transport.http import PreparedRequest
from myrm_agent_harness.toolkits.llms.transport.profile import Route, resolve_route
from myrm_agent_harness.toolkits.llms.transport.retry import DEFAULT_RETRIES

_HI = [{"role": "user", "content": "hi"}]
_AZURE = "https://resource.openai.azure.com"


def _chat(route: Route) -> PreparedRequest:
    return openai_chat.prepare(route, _HI, {})


def _responses(route: Route) -> PreparedRequest:
    return openai_responses.prepare(route, {"input": "hi"})


def _anthropic(route: Route) -> PreparedRequest:
    return anthropic_messages.prepare(route, _HI, {})


def _gemini(route: Route) -> PreparedRequest:
    return gemini_generate.prepare(route, _HI, {})


def _ollama(route: Route) -> PreparedRequest:
    return ollama_chat.prepare(route, _HI, {})


_MODEL_CALLS: list[tuple[str, str | None, Callable[[Route], PreparedRequest]]] = [
    ("openai/gpt-4o", None, _chat),
    ("azure/gpt-4o", _AZURE, _chat),
    ("openai/gpt-5.4", None, _responses),
    ("anthropic/claude-sonnet-4-5", None, _anthropic),
    ("gemini/gemini-2.5-pro", None, _gemini),
    ("ollama/llama3.1", None, _ollama),
]


class TestModelCalls:
    @pytest.mark.parametrize(("model", "api_base", "prepare"), _MODEL_CALLS, ids=[case[0] for case in _MODEL_CALLS])
    def test_every_model_call_wire_allows_the_default_retries(
        self, model: str, api_base: str | None, prepare: Callable[[Route], PreparedRequest]
    ) -> None:
        request = prepare(resolve_route(model, api_key="k", api_base=api_base))

        assert request.retries == DEFAULT_RETRIES == 2


class TestServiceCalls:
    """Embeddings retry in ``CloudEmbedding`` and images in ``ImageGenerator``; a second layer would multiply them."""

    @pytest.fixture
    def sent(self, monkeypatch: pytest.MonkeyPatch) -> list[PreparedRequest]:
        requests: list[PreparedRequest] = []
        answers: dict[str, Mapping[str, object]] = {
            "embeddings": {"data": [{"index": 0, "embedding": [0.1]}]},
            "cohere": {"embeddings": {"float": [[0.1]]}},
            "gemini": {"embeddings": [{"values": [0.1]}]},
        }

        async def capture_embedding(request: PreparedRequest) -> dict[str, object]:
            requests.append(request)
            return dict(answers[request.provider if request.provider in answers else "embeddings"])

        async def capture_rerank(request: PreparedRequest) -> dict[str, object]:
            requests.append(request)
            return {"results": [{"index": 0, "relevance_score": 0.5}]}

        async def capture_image(request: PreparedRequest) -> dict[str, object]:
            requests.append(request)
            return {"data": [{"url": "https://img.example/1.png"}]}

        monkeypatch.setattr(embeddings, "asend_json", capture_embedding)
        monkeypatch.setattr(rerank, "asend_json", capture_rerank)
        monkeypatch.setattr(images, "asend_json", capture_image)
        return requests

    @pytest.mark.parametrize(
        "model", ["openai/text-embedding-3-small", "cohere/embed-v4.0", "gemini/text-embedding-004"]
    )
    async def test_embeddings_are_sent_once(self, sent: list[PreparedRequest], model: str) -> None:
        await embeddings.aembed(model, ["a"], api_key="k")

        assert [request.retries for request in sent] == [0]

    async def test_rerank_is_sent_once(self, sent: list[PreparedRequest]) -> None:
        await rerank.arerank("cohere/rerank-v3.5", "q", ["a"], top_n=1, api_key="k")

        assert [request.retries for request in sent] == [0]

    async def test_image_generation_and_editing_are_sent_once(self, sent: list[PreparedRequest]) -> None:
        common = {"size": "1024x1024", "n": 1, "api_key": "k", "api_base": None, "timeout": 30.0}
        await images.agenerate_images("openai/gpt-image-1", "a cat", quality=None, style=None, **common)
        await images.aedit_images("openai/gpt-image-1", b"\x89PNG\r\n\x1a\n", "a hat", mask=None, **common)

        assert [request.retries for request in sent] == [0, 0]


class TestMalformedAnswers:
    def test_an_answer_that_is_not_json_is_a_provider_fault_the_agent_layer_may_fail_over_from(self) -> None:
        kind = classify_error(LLMResponseError("openai", "answered with HTML"))

        assert kind is ErrorKind.OVERLOADED
        assert kind.is_failoverable
