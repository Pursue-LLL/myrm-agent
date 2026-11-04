"""Rerank calls: the ``/rerank`` shape of Cohere, Jina, Together, SiliconFlow and compatible gateways, and Voyage's variant.

[INPUT]
- transport.service_routes (POS: service_route — provider, endpoint and credential)
- transport.http (POS: PreparedRequest, asend_json)
- transport.answer_cache (POS: replays the ranking of a query that was already ranked)

[OUTPUT]
- arerank: (document index, relevance score) pairs, best first

[POS]
All rerank providers take ``{model, query, documents}`` and answer with ``index`` / ``relevance_score`` entries.
Voyage names the limit ``top_k`` and wraps the entries in ``data`` instead of ``results``; everything else shares one path.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

from myrm_agent_harness.toolkits.llms.transport.answer_cache import acached_answer
from myrm_agent_harness.toolkits.llms.transport.http import PreparedRequest, asend_json
from myrm_agent_harness.toolkits.llms.transport.profile import UnsupportedProviderError
from myrm_agent_harness.toolkits.llms.transport.service_routes import service_route

_TIMEOUT_SECONDS: Final = 60.0


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


async def _scored(request: PreparedRequest, provider: str, document_count: int) -> list[tuple[int, float]]:
    payload = await asend_json(request)
    return [_pair(entry, document_count) for entry in _entries(payload, provider)]


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
        provider=provider, url=f"{route.base_url}/rerank", headers=headers, body=body, timeout=_TIMEOUT_SECONDS
    )
    pairs = await acached_answer(request, lambda: _scored(request, provider, len(documents)))
    return [(int(index), float(score)) for index, score in pairs]  # a stored ranking comes back as JSON lists
