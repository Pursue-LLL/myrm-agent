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

    async def rerank_pairs(
        self,
        pairs: list[tuple[str, str]],
    ) -> list[float]:
        """Score each (query, document) pair, one provider call per distinct query.

        Pairs are grouped by query and the groups are reranked concurrently. A provider answers with hits ranked by
        relevance, each labelled with the index of the document it scored, so a hit's score goes to the pair that
        document came from, not to the pair at the hit's position in the answer. A document the provider leaves out
        of its answer scores 0.0.

        Args:
            pairs: (query, document) pairs.

        Returns:
            One relevance score per pair, in the order of ``pairs``.

        Raises:
            ValueError: A hit is labelled with an index outside the documents sent for its query.
        """
        if not pairs:
            return []

        start_time = time.perf_counter()
        positions_by_query: dict[str, list[int]] = {}
        for position, (query, _) in enumerate(pairs):
            positions_by_query.setdefault(query, []).append(position)

        scores = [0.0] * len(pairs)

        async def score_query(query: str, positions: list[int]) -> None:
            documents = [pairs[position][1] for position in positions]
            hits = await self.rerank(query, documents, top_k=len(documents))
            for hit in hits:
                if not 0 <= hit.index < len(documents):
                    raise ValueError(
                        f"Reranker labelled a hit with index {hit.index}, "
                        f"outside the {len(documents)} documents sent for the query"
                    )
                scores[positions[hit.index]] = hit.score

        await asyncio.gather(*(score_query(query, positions) for query, positions in positions_by_query.items()))

        logger.info(
            "Reranked %d pairs across %d queries in %.2fs (model: %s)",
            len(pairs),
            len(positions_by_query),
            time.perf_counter() - start_time,
            self._model,
        )
        return scores

    async def rerank(self, query: str, documents: list[str], top_k: int | None = None) -> list[RerankResult]:
        """Rerank ``documents`` for ``query``: ``top_k`` (all when None) is the result limit asked of the provider.

        The hits come back as the provider answered: in its order, and as many as it sent (a provider that ignores
        the limit answers with more than ``top_k``).

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
        return [RerankResult(index=index, score=score, text=documents[index]) for index, score in ranked]
