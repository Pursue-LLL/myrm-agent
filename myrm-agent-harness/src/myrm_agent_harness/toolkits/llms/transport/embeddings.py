"""Embedding calls: OpenAI-compatible ``/embeddings``, Cohere ``/embed`` and Gemini ``:batchEmbedContents``.

[INPUT]
- transport.service_routes (POS: service_route — provider, endpoint and credential)
- transport.openai_chat (POS: openai_endpoint — URL and auth headers of an OpenAI-family path)
- transport.http (POS: PreparedRequest, asend_json)

[OUTPUT]
- aembed: vectors for a batch of texts, in input order

[POS]
Every provider the settings offer for embeddings speaks the OpenAI ``/embeddings`` shape (OpenAI, Azure, Jina,
Voyage, SiliconFlow, Ollama, any compatible gateway) except Cohere, which has its own ``/embed``, and Gemini, which
has ``:batchEmbedContents``. Each is one request and one parse here, so the retriever depends on a function instead
of a provider SDK. A custom ``api_base`` is an OpenAI-compatible gateway and keeps the whole model id.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

from myrm_agent_harness.toolkits.llms.transport.http import PreparedRequest, asend_json
from myrm_agent_harness.toolkits.llms.transport.openai_chat import openai_endpoint
from myrm_agent_harness.toolkits.llms.transport.params import split_params
from myrm_agent_harness.toolkits.llms.transport.profile import Route
from myrm_agent_harness.toolkits.llms.transport.service_routes import service_route

_TIMEOUT_SECONDS: Final = 60.0
# Voyage and Jina return float arrays by default; omitting the field is accepted by every API version.
_NO_ENCODING_FORMAT: Final = frozenset({"voyage", "jina_ai"})


def _vector(item: object) -> list[float]:
    if not isinstance(item, list):
        raise ValueError("Embedding provider returned a malformed vector")
    return [float(x) for x in item]


def _openai_request(route: Route, texts: Sequence[str]) -> PreparedRequest:
    base = route.base_url
    if base and route.profile.wire == "ollama":  # Ollama serves the OpenAI shape under /v1
        route = Route(route.profile, route.model, f"{base}/v1", route.api_key)
    url, query, headers = openai_endpoint(route, split_params({}), "/embeddings")
    body: dict[str, object] = {"model": route.model, "input": list(texts)}
    if route.profile.id not in _NO_ENCODING_FORMAT:
        body["encoding_format"] = "float"
    return PreparedRequest(
        provider=route.profile.id, url=url, headers=headers, body=body, timeout=_TIMEOUT_SECONDS, query=query
    )


def _parse_openai(payload: dict[str, object], expected: int) -> list[list[float]]:
    data = payload.get("data")
    if not isinstance(data, list) or len(data) != expected:
        raise ValueError(
            f"Embedding provider returned {len(data) if isinstance(data, list) else 'no'} vectors for {expected} inputs"
        )
    ordered = sorted((d for d in data if isinstance(d, dict)), key=lambda d: int(d.get("index", 0)))
    return [_vector(d.get("embedding")) for d in ordered]


def _cohere_request(route: Route, texts: Sequence[str]) -> PreparedRequest:
    headers = {"Authorization": f"Bearer {route.api_key}"} if route.api_key else {}
    body: dict[str, object] = {
        "model": route.model,
        "texts": list(texts),
        "input_type": "search_document",
        "embedding_types": ["float"],
    }
    return PreparedRequest(
        provider="cohere", url=f"{route.base_url}/embed", headers=headers, body=body, timeout=_TIMEOUT_SECONDS
    )


def _parse_cohere(payload: dict[str, object], expected: int) -> list[list[float]]:
    embeddings = payload.get("embeddings")
    vectors = embeddings.get("float") if isinstance(embeddings, dict) else embeddings
    if not isinstance(vectors, list) or len(vectors) != expected:
        raise ValueError("Cohere returned a malformed embeddings payload")
    return [_vector(v) for v in vectors]


def _gemini_request(route: Route, texts: Sequence[str]) -> PreparedRequest:
    requests = [{"model": f"models/{route.model}", "content": {"parts": [{"text": t}]}} for t in texts]
    headers = {"x-goog-api-key": route.api_key} if route.api_key else {}
    return PreparedRequest(
        provider="gemini",
        url=f"{route.base_url}/models/{route.model}:batchEmbedContents",
        headers=headers,
        body={"requests": requests},
        timeout=_TIMEOUT_SECONDS,
    )


def _parse_gemini(payload: dict[str, object], expected: int) -> list[list[float]]:
    embeddings = payload.get("embeddings")
    if not isinstance(embeddings, list) or len(embeddings) != expected:
        raise ValueError("Gemini returned a malformed embeddings payload")
    return [_vector(e.get("values") if isinstance(e, dict) else None) for e in embeddings]


async def aembed(
    model: str, texts: Sequence[str], *, api_key: str | None = None, api_base: str | None = None
) -> list[list[float]]:
    """Vectors for ``texts`` in input order; raises LLMHTTPError on a refused call."""
    route = service_route(model, api_key=api_key, api_base=api_base, gateway_base=True)
    if route.profile.id == "cohere":
        return _parse_cohere(await asend_json(_cohere_request(route, texts)), len(texts))
    if route.profile.wire == "gemini":
        return _parse_gemini(await asend_json(_gemini_request(route, texts)), len(texts))
    return _parse_openai(await asend_json(_openai_request(route, texts)), len(texts))
