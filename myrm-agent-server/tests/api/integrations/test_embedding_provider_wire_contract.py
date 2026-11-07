"""What each embedding provider receives on the wire from the real CloudEmbedding and LiteLLM.

CloudEmbedding builds the call parameters and LiteLLM's per-provider adapters turn them into the request body that the
provider's API judges. The parameters CloudEmbedding really builds run through the real LiteLLM, with the defaults the
server runs with, against a loopback provider that records the body.

Voyage's API takes `encoding_format` as null or "base64" (docs.voyageai.com/reference/embeddings-api); a request with
"float" got HTTP 400 on 2026-11-07, one without it returned floats. The other providers' bodies are pinned as they are
today, so a change to one of them is a deliberate decision.
"""

from __future__ import annotations

from collections.abc import Iterator
from types import SimpleNamespace
from unittest.mock import patch

import litellm
import pytest
from myrm_agent_harness.toolkits.retriever.embedding.cloud_embedding import CloudEmbedding

from tests.support.fake_retrieval_provider import FakeRetrievalProvider, fake_retrieval_provider


@pytest.fixture(autouse=True)
def server_litellm_defaults() -> None:
    # The first import of the llms package applies the LiteLLM defaults the server runs with (drop_params).
    from myrm_agent_harness.toolkits.llms import llm_manager  # noqa: F401


@pytest.fixture
def provider() -> Iterator[FakeRetrievalProvider]:
    with fake_retrieval_provider() as running:
        yield running


async def _wire_body(provider: FakeRetrievalProvider, model: str, api_base: str | None = None) -> dict[str, object]:
    """The request body LiteLLM posts for the call CloudEmbedding builds for `model`, the loopback standing in for the provider."""
    built: list[dict[str, object]] = []

    async def record(**kwargs: object) -> SimpleNamespace:
        built.append(kwargs)
        return SimpleNamespace(data=[{"embedding": [0.1] * 4}])

    with patch("litellm.aembedding", side_effect=record):
        await CloudEmbedding(model=model, api_key="sk-loopback", api_base=api_base).embed("hello")

    [kwargs] = built
    try:
        await litellm.aembedding(**{**kwargs, "api_base": provider.api_base})
    except litellm.APIConnectionError:
        # An adapter that expects another response shape than the OpenAI one the loopback answers with (Cohere)
        # cannot parse it; the request, which is what is judged here, was recorded before that.
        pass
    assert provider.requests, f"no request reached the provider for {model}"
    return provider.requests[-1].body


async def test_voyage_receives_no_encoding_format(provider: FakeRetrievalProvider) -> None:
    body = await _wire_body(provider, "voyage/voyage-4-lite")

    assert "encoding_format" not in body, body


@pytest.mark.parametrize(
    ("model", "api_base"),
    [("openai/BAAI/bge-m3", "https://api.siliconflow.cn/v1"), ("text-embedding-3-small", None)],
)
async def test_openai_style_providers_receive_float(provider: FakeRetrievalProvider, model: str, api_base: str | None) -> None:
    body = await _wire_body(provider, model, api_base)

    assert body["encoding_format"] == "float", body


async def test_cohere_receives_float_embedding_types(provider: FakeRetrievalProvider) -> None:
    body = await _wire_body(provider, "cohere/embed-multilingual-v3.0")

    assert body["embedding_types"] == ["float"], body


async def test_jina_receives_no_encoding_format(provider: FakeRetrievalProvider) -> None:
    body = await _wire_body(provider, "jina_ai/jina-embeddings-v3")

    assert "encoding_format" not in body, body
