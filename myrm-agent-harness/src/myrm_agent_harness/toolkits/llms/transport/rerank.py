"""Rerank calls: the ``/rerank`` shape of Cohere, Jina, Together, SiliconFlow and compatible gateways, and Voyage's variant.

[INPUT]
- transport.service_routes (POS: service_route — provider, endpoint and credential)
- transport.http (POS: PreparedRequest, asend_json)

[OUTPUT]
- arerank: (document index, relevance score) pairs, best first

[POS]
All rerank providers take ``{model, query, documents}`` and answer with ``index`` / ``relevance_score`` entries.
Voyage names the limit ``top_k`` and wraps the entries in ``data`` instead of ``results``; everything else shares one path.
Cohere, Jina and Voyage serve rerank under a version segment, so an endpoint that stops at a host or a gateway prefix
(``COHERE_API_BASE=https://gateway``) is completed with it; an endpoint that already ends in one is used as given.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Final

from myrm_agent_harness.toolkits.llms.transport.http import PreparedRequest, asend_json
from myrm_agent_harness.toolkits.llms.transport.profile import UnsupportedProviderError
from myrm_agent_harness.toolkits.llms.transport.service_routes import service_route

_TIMEOUT_SECONDS: Final = 60.0
_API_PATH: Final = {"cohere": "/v2", "jina_ai": "/v1", "voyage": "/v1"}
_VERSION_SEGMENT: Final = re.compile(r"/v\d+$")


def _rerank_url(provider: str, base_url: str) -> str:
    api_path = _API_PATH.get(provider, "")
    if api_path and not _VERSION_SEGMENT.search(base_url):
        base_url += api_path
    return f"{base_url}/rerank"


def _entries(payload: dict[str, object], provider: str) -> list[object]:
    entries = payload.get("data" if provider == "voyage" else "results")
    if not isinstance(entries, list):
        raise ValueError(f"{provider} rerank answered without a result list")
    return entries


def _pair(entry: object, document_count: int) -> tuple[int, float]:
    if not isinstance(entry, dict):
        raise ValueError("Rerank provider returned a malformed result entry")
    index, score = entry.get("index"), entry.get("relevance_score")
    if not isinstance(index, int) or not 0 <= index < document_count or not isinstance(score, (int, float)):
        raise ValueError("Rerank provider returned a result entry that does not match the documents")
    return index, float(score)


async def arerank(
    model: str,
    query: str,
    documents: Sequence[str],
    *,
    top_n: int,
    api_key: str | None = None,
    api_base: str | None = None,
) -> list[tuple[int, float]]:
    """Score ``documents`` against ``query``; raises LLMHTTPError on a refused call."""
    route = service_route(model, api_key=api_key, api_base=api_base)
    provider = route.profile.id
    if not route.base_url:
        raise UnsupportedProviderError(f"Provider '{provider}' needs an api_base: it has no default rerank endpoint")
    body: dict[str, object] = {"model": route.model, "query": query, "documents": list(documents)}
    body["top_k" if provider == "voyage" else "top_n"] = top_n
    headers = {"Authorization": f"Bearer {route.api_key}"} if route.api_key else {}
    request = PreparedRequest(
        provider=provider,
        url=_rerank_url(provider, route.base_url),
        headers=headers,
        body=body,
        timeout=_TIMEOUT_SECONDS,
    )
    payload = await asend_json(request)
    return [_pair(entry, len(documents)) for entry in _entries(payload, provider)]
