"""Cloud Reranker Implementation.

Cloud rerank backend for Cohere, Jina AI, Voyage AI, Together AI, SiliconFlow and any OpenAI-compatible
``/rerank`` endpoint.

[INPUT]
- .base::RerankerService / RerankResult (POS: Reranker contract layer)
- toolkits.llms.transport::arerank (POS: provider request and response handling)

[OUTPUT]
- CloudReranker: Concrete RerankerService backed by cloud rerank APIs

[POS]
Cloud reranker backend. Translates the abstract RerankerService interface into rerank API calls; the provider
shape (endpoint, credential, field names) is the transport's concern, not this class's.
"""

from __future__ import annotations

import asyncio
import logging
import time

from myrm_agent_harness.toolkits.llms.transport.rerank import arerank
from myrm_agent_harness.toolkits.retriever.reranker.base import RerankerService, RerankResult

logger = logging.getLogger(__name__)


class CloudReranker(RerankerService):
    """Reranker over a cloud rerank API.

    Example:
        ```python
        service = CloudReranker(model="cohere/rerank-v3.5", api_key="xxx")
        service = CloudReranker(model="jina_ai/jina-reranker-v2-base-multilingual", api_key="xxx")
        service = CloudReranker(model="voyage/rerank-2", api_key="xxx")
        # Any other provider: the model id is sent as-is to ``{api_base}/rerank``.
        service = CloudReranker(
            model="BAAI/bge-reranker-v2-m3", api_key="sk-xxx", api_base="https://api.siliconflow.cn/v1"
        )
        results = await service.rerank(query="What is AI?", documents=["AI is...", "Machine learning..."], top_k=5)
        ```
    """

    def __init__(
        self,
        model: str = "cohere/rerank-v3.5",
        api_key: str | None = None,
        api_base: str | None = None,
    ):
        """Args:
        model: ``provider/model`` (``cohere/rerank-v3.5``), or a bare model id together with ``api_base``.
        api_key: Provider API key.
        api_base: Custom endpoint root; required for providers without a built-in endpoint.
        """
        self._model = model
        self._api_key = api_key
        self._api_base = api_base
        logger.info("Cloud reranker initialized: %s", model)

    async def rerank_pairs(self, pairs: list[tuple[str, str]]) -> list[float]:
        """Score (query, document) pairs; pairs of one query share a single API call, queries run concurrently."""
        if not pairs:
            return []

        start_time = time.monotonic()
        documents_by_query: dict[str, list[tuple[int, str]]] = {}
        for index, (query, document) in enumerate(pairs):
            documents_by_query.setdefault(query, []).append((index, document))

        logger.debug(
            "Batch rerank: %d pairs, %d queries (model: %s, api_base: %s)",
            len(pairs),
            len(documents_by_query),
            self._model,
            self._api_base or "default",
        )

        async def rerank_query(query: str, indexed: list[tuple[int, str]]) -> list[tuple[int, float]]:
            results = await self.rerank(query, [document for _, document in indexed], top_k=len(indexed))
            return [(indexed[result.index][0], result.score) for result in results]

        scores = [0.0] * len(pairs)
        for query_results in await asyncio.gather(*(rerank_query(q, d) for q, d in documents_by_query.items())):
            for pair_index, score in query_results:
                scores[pair_index] = score

        logger.debug("Batch rerank done in %.2fs", time.monotonic() - start_time)
        return scores

    async def rerank(self, query: str, documents: list[str], top_k: int | None = None) -> list[RerankResult]:
        """Rerank ``documents`` for ``query``; the best ``top_k`` (all when None) come back by score, descending.

        Raises:
            LLMHTTPError: The provider refused the call.
            ValueError: The provider answered in an unexpected shape.
        """
        if not documents:
            return []
        limit = len(documents) if top_k is None else top_k
        try:
            ranked = await arerank(
                self._model, query, documents, top_n=limit, api_key=self._api_key, api_base=self._api_base
            )
        except Exception as exc:
            logger.warning("Rerank call failed for model %s: %s: %s", self._model, type(exc).__name__, exc)
            raise
        if not ranked:
            logger.warning("Rerank returned no results for model %s", self._model)
            return []
        ranked.sort(key=lambda pair: pair[1], reverse=True)
        return [RerankResult(index=index, score=score, text=documents[index]) for index, score in ranked[:limit]]
