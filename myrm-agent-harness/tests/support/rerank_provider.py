"""A fake OpenAI-compatible ``/rerank`` endpoint, so the real ``CloudReranker`` runs with only the network replaced.

[INPUT]
- myrm_agent_harness.toolkits.retriever.reranker.cloud_reranker::CloudReranker (POS: cloud reranker backend)

[OUTPUT]
- Relevance: the score a document earns for a query, keyed by ``(query, document)``
- provider_reranker: an async context manager yielding a ``CloudReranker`` served by that endpoint

[POS]
Pytest-only helper shared by the reranker tests. A provider ranks the hits it returns by relevance and labels each
hit with the index of the document it scored, so a test over this endpoint tells a backfill that follows the label
from one that follows the position; a double that answers in input order, or one built by overriding ``rerank_pairs``,
cannot.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from typing import cast

import httpx

from myrm_agent_harness.toolkits.retriever.reranker.cloud_reranker import CloudReranker

Relevance = Mapping[tuple[str, str], float]


def _provider_transport(relevance: Relevance, omit: frozenset[str]) -> httpx.MockTransport:
    """Answer ``POST /rerank`` with hits ranked by relevance, each labelled with its document's index."""

    def answer(request: httpx.Request) -> httpx.Response:
        body = cast("dict[str, object]", json.loads(request.content))
        query = cast("str", body["query"])
        documents = cast("list[str]", body["documents"])
        hits = [
            {"index": index, "relevance_score": relevance[(query, document)]}
            for index, document in enumerate(documents)
            if document not in omit
        ]
        hits.sort(key=lambda hit: hit["relevance_score"], reverse=True)
        return httpx.Response(200, json={"results": hits})

    return httpx.MockTransport(answer)


@asynccontextmanager
async def provider_reranker(
    relevance: Relevance, *, omit: frozenset[str] = frozenset()
) -> AsyncIterator[CloudReranker]:
    """A ``CloudReranker`` talking to the fake provider; ``omit`` lists documents the provider leaves out of its answers."""
    reranker = CloudReranker(model="openai/test-reranker", api_key="test-key", api_base="https://rerank.test/v1")
    reranker._http_client = httpx.AsyncClient(transport=_provider_transport(relevance, omit))
    try:
        yield reranker
    finally:
        await reranker.aclose()
