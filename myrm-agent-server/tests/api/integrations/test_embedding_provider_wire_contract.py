"""What each embedding provider receives on the wire from the real CloudEmbedding and the transport.

CloudEmbedding hands its model, key and endpoint to the transport, which builds the request body each provider's API
judges. The real classes run against a loopback provider that records the body that arrived over HTTP. A provider is
reached through its own endpoint variable (`VOYAGE_API_BASE`, `JINA_AI_API_BASE`, `COHERE_API_BASE`) so the request keeps
that provider's profile; a custom `api_base` is an OpenAI-compatible gateway that keeps the whole model id.

Voyage's API takes `encoding_format` as null or "base64" (docs.voyageai.com/reference/embeddings-api); a request with
"float" got HTTP 400 on 2026-11-07, one without it returned floats. The other providers' bodies are pinned as they are
today, so a change to one of them is a deliberate decision.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from myrm_agent_harness.toolkits.retriever.embedding.cloud_embedding import CloudEmbedding

from tests.support.fake_retrieval_provider import FakeRetrievalProvider, ProviderRequest, fake_retrieval_provider


@pytest.fixture
def provider() -> Iterator[FakeRetrievalProvider]:
    with fake_retrieval_provider() as running:
        yield running


async def _wire_request(provider: FakeRetrievalProvider, model: str, api_base: str | None = None) -> ProviderRequest:
    """The request that reaches the loopback when CloudEmbedding embeds one text with `model`."""
    await CloudEmbedding(model=model, api_key="sk-loopback", api_base=api_base, max_retries=0).embed("hello")
    assert provider.requests, f"no request reached the provider for {model}"
    return provider.requests[-1]


async def test_voyage_receives_no_encoding_format(provider: FakeRetrievalProvider, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VOYAGE_API_BASE", provider.api_base)

    request = await _wire_request(provider, "voyage/voyage-4-lite")

    assert request.path == "/v1/embeddings"
    assert request.body == {"model": "voyage-4-lite", "input": ["hello"]}, request.body


@pytest.mark.parametrize(
    ("model", "wire_model"),
    [("openai/BAAI/bge-m3", "BAAI/bge-m3"), ("text-embedding-3-small", "text-embedding-3-small")],
)
async def test_openai_style_providers_receive_float(provider: FakeRetrievalProvider, model: str, wire_model: str) -> None:
    request = await _wire_request(provider, model, provider.api_base)

    assert request.body == {"model": wire_model, "input": ["hello"], "encoding_format": "float"}, request.body


async def test_a_voyage_model_behind_a_custom_endpoint_receives_float_and_the_whole_model_id(
    provider: FakeRetrievalProvider,
) -> None:
    request = await _wire_request(provider, "voyage/voyage-4-lite", provider.api_base)

    assert request.body == {"model": "voyage/voyage-4-lite", "input": ["hello"], "encoding_format": "float"}, request.body


async def test_cohere_receives_float_embedding_types(provider: FakeRetrievalProvider, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COHERE_API_BASE", provider.api_base)

    request = await _wire_request(provider, "cohere/embed-multilingual-v3.0")

    assert request.path == "/v1/embed"
    assert request.body["embedding_types"] == ["float"], request.body
    assert "encoding_format" not in request.body, request.body


async def test_jina_receives_no_encoding_format(provider: FakeRetrievalProvider, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JINA_AI_API_BASE", provider.api_base)

    request = await _wire_request(provider, "jina_ai/jina-embeddings-v3")

    assert request.path == "/v1/embeddings"
    assert request.body == {"model": "jina-embeddings-v3", "input": ["hello"]}, request.body
