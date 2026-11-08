"""CloudEmbedding sends each provider only the request parameters its embeddings API accepts.

Voyage's API takes `encoding_format` as null or "base64" and answers HTTP 400 to "float", while the OpenAI-style
providers (OpenAI, OpenAI-compatible endpoints such as SiliconFlow) are sent `float`; Cohere carries the same wish as
`embedding_types` and Jina is sent no `encoding_format`. CloudEmbedding adds nothing of its own: the request the
transport builds from its model, key and endpoint is what each provider receives. The bodies that arrive over HTTP are
asserted in the server suite (`tests/api/integrations/test_embedding_provider_wire_contract.py`).
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from myrm_agent_harness.toolkits.llms.transport import embeddings
from myrm_agent_harness.toolkits.llms.transport.http import PreparedRequest
from myrm_agent_harness.toolkits.retriever.embedding.cloud_embedding import CloudEmbedding

_API_KEY = "sk-test"
_VECTOR = [0.1] * 4


@pytest.fixture
def requests_sent(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[PreparedRequest]]:
    """The requests the transport is asked to send; each is answered with one vector per input, in the provider's shape."""
    sent: list[PreparedRequest] = []

    async def fake_send(request: PreparedRequest) -> dict[str, object]:
        sent.append(request)
        cohere = request.provider == "cohere"
        inputs = (request.body or {}).get("texts" if cohere else "input")
        assert isinstance(inputs, list)
        if cohere:
            return {"embeddings": {"float": [_VECTOR for _ in inputs]}}
        return {"data": [{"index": index, "embedding": _VECTOR} for index in range(len(inputs))]}

    monkeypatch.setattr(embeddings, "asend_json", fake_send)
    yield sent


async def _request(sent: list[PreparedRequest], model: str, api_base: str | None = None) -> PreparedRequest:
    """The one request CloudEmbedding makes to embed a single text."""
    await CloudEmbedding(model=model, api_key=_API_KEY, api_base=api_base).embed("hello")
    [request] = sent
    return request


@pytest.mark.parametrize("model", ["voyage/voyage-4-lite", "voyage/voyage-3"])
async def test_voyage_is_not_sent_an_encoding_format(requests_sent: list[PreparedRequest], model: str) -> None:
    request = await _request(requests_sent, model)

    assert request.url == "https://api.voyageai.com/v1/embeddings"
    assert request.body == {"model": model.removeprefix("voyage/"), "input": ["hello"]}


@pytest.mark.parametrize(
    ("model", "api_base", "wire_model"),
    [
        ("openai/BAAI/bge-m3", "https://api.siliconflow.cn/v1", "BAAI/bge-m3"),
        ("BAAI/bge-m3", "https://api.siliconflow.cn/v1", "BAAI/bge-m3"),
        ("text-embedding-3-small", None, "text-embedding-3-small"),
    ],
)
async def test_openai_style_providers_are_sent_float(
    requests_sent: list[PreparedRequest], model: str, api_base: str | None, wire_model: str
) -> None:
    request = await _request(requests_sent, model, api_base)

    assert request.body == {"model": wire_model, "input": ["hello"], "encoding_format": "float"}


async def test_cohere_is_sent_float_embedding_types(requests_sent: list[PreparedRequest]) -> None:
    request = await _request(requests_sent, "cohere/embed-multilingual-v3.0")

    assert request.body is not None
    assert request.body["embedding_types"] == ["float"]
    assert "encoding_format" not in request.body


async def test_jina_is_not_sent_an_encoding_format(requests_sent: list[PreparedRequest]) -> None:
    request = await _request(requests_sent, "jina_ai/jina-embeddings-v3")

    assert request.url == "https://api.jina.ai/v1/embeddings"
    assert request.body == {"model": "jina-embeddings-v3", "input": ["hello"]}


async def test_a_voyage_model_behind_a_custom_endpoint_is_an_openai_compatible_request(
    requests_sent: list[PreparedRequest],
) -> None:
    # A custom api_base is an OpenAI-compatible gateway that routes on the whole model id, whatever the prefix.
    request = await _request(requests_sent, "voyage/voyage-3", "https://gateway.example/v1")

    assert request.url == "https://gateway.example/v1/embeddings"
    assert request.body == {"model": "voyage/voyage-3", "input": ["hello"], "encoding_format": "float"}


async def test_a_blank_text_is_sent_as_a_space(requests_sent: list[PreparedRequest]) -> None:
    # Providers reject an empty string, so the input keeps its position as a single space.
    await CloudEmbedding(model="text-embedding-3-small", api_key=_API_KEY).embed_batch(["alpha", "", "gamma"])

    [request] = requests_sent
    assert request.body is not None
    assert request.body["input"] == ["alpha", " ", "gamma"]
