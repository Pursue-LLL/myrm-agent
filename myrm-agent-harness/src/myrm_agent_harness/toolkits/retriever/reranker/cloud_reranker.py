"""Cloud Reranker Implementation.

Cloud API reranking backend supporting multiple providers:
- LiteLLM-supported providers: Cohere, Jina AI, Voyage AI, etc.
- OpenAI-compatible providers: direct HTTP calls (SiliconFlow, etc.)

[INPUT]
- .base::RerankerService (POS: Reranker contract layer)
- .base::RerankResult (POS: Reranker contract layer)

[OUTPUT]
- CloudReranker: Concrete RerankerService backed by cloud APIs via LiteLLM or direct HTTP

[POS]
Cloud reranker backend. Translates the abstract RerankerService interface into real
API calls with support for both LiteLLM-managed and OpenAI-compatible endpoints.

"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    import httpx
    from litellm.types.rerank import RerankResponse

from myrm_agent_harness.toolkits.retriever.reranker.base import RerankerService, RerankResult

logger = logging.getLogger(__name__)


class CloudReranker(RerankerService):
    """Cloud端 API 重Sortimplements

     via  LiteLLM 统一Call各种Cloud端重Sort API。
    Support Cohere、Jina AI、Voyage AI、Together AI、SiliconFlow  etc.provides商。

    Example:
        ```python
        #  using  Cohere
        service = CloudReranker(
            model="cohere/rerank-v3.5",
            api_key="xxx"
        )

        #  using  Jina AI
        service = CloudReranker(
            model="jina_ai/jina-reranker-v2-base-multilingual",
            api_key="xxx"
        )

        #  using  Voyage AI
        service = CloudReranker(
            model="voyage/rerank-2",
            api_key="xxx"
        )

        #  using  SiliconFlow
        service = CloudReranker(
            model="siliconflow/BAAI/bge-reranker-v2-m3",
            api_key="sk-xxx",
            api_base="https://api.siliconflow.cn/v1"
        )

        results = await service.rerank(
            query="What is AI?",
            documents=["AI is...", "Machine learning..."],
            top_k=5
        )
        ```
    """

    def __init__(
        self,
        model: str = "cohere/rerank-v3.5",
        api_key: str | None = None,
        api_base: str | None = None,
    ):
        """InitializeCloud端重SortService

        Args:
            model: 模型名称（LiteLLM Format，如 "cohere/rerank-v3.5" or  "jina_ai/jina-reranker-v2-base-multilingual"）
            api_key: API Key
            api_base: custom API 端点（optional）
        """
        self._model = model
        self._api_key = api_key
        self._api_base = api_base
        self._http_client: httpx.AsyncClient | None = None

        logger.info(f" Cloud reranker initialized: {model}")

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

    async def rerank(
        self,
        query: str,
        documents: list[str],
        top_k: int | None = None,
    ) -> list[RerankResult]:
        """重Sort文档

        智能路由：
        - OpenAI compatible模型（如 SiliconFlow）： directly  HTTP Call
        - LiteLLM Support 模型： via  LiteLLM Call

        Args:
            query: Querytext
            documents: 文档List
            top_k: Return前 k 个Result，None 表示ReturnAll

        Returns:
            按分数降序排列 重SortResultList

        Raises:
            ImportError: If litellm  not yet 安装
            ValueError: IfParameterInvalid or  API ReturnFormatException
        """
        if not documents:
            return []

        if top_k is None:
            top_k = len(documents)

        # 检测Whether is  OpenAI compatible模型（ need  directly  HTTP Call）
        if self._is_openai_compatible():
            return await self._rerank_openai_compatible(query, documents, top_k)
        else:
            return await self._rerank_litellm(query, documents, top_k)

    def _is_openai_compatible(self) -> bool:
        """检测Whether is  OpenAI compatible模型"""
        # OpenAI compatible 特征： has  api_base 且模型Format特殊
        if not self._api_base:
            return False

        # SiliconFlow  or Other using  openai/ Prefix 模型
        return self._model.startswith("openai/") or "siliconflow" in self._api_base.lower()

    def _get_http_client(self) -> httpx.AsyncClient:
        """Get or Create持久 HTTP Client（Connection池optimized）"""
        if self._http_client is None:
            import httpx

            from myrm_agent_harness.infra.tls_compat import create_httpx_client

            self._http_client = create_httpx_client(
                timeout=60.0,
                limits=httpx.Limits(max_keepalive_connections=10, max_connections=20),
            )
        return self._http_client

    async def aclose(self) -> None:
        """Close HTTP ClientConnection"""
        if self._http_client is not None:
            await self._http_client.aclose()
            self._http_client = None

    async def _rerank_openai_compatible(
        self,
        query: str,
        documents: list[str],
        top_k: int,
    ) -> list[RerankResult]:
        """directly Call OpenAI compatible  rerank API（Connection池optimized）"""
        # Extractreal 模型名（去掉 openai/ Prefix）
        model_name = self._model.replace("openai/", "")

        url = f"{self._api_base}/rerank"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model_name,
            "query": query,
            "documents": documents,
            "top_n": top_k,
        }

        try:
            client = self._get_http_client()
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()

            # ParseResponse
            results = []
            for item in data.get("results", []):
                results.append(
                    RerankResult(
                        index=item["index"],
                        score=item["relevance_score"],
                        text=documents[item["index"]],
                    )
                )
            return results

        except Exception as e:
            logger.warning(f"Failed to call OpenAI-compatible rerank API: {type(e).__name__}: {e}")
            raise

    async def _rerank_litellm(
        self,
        query: str,
        documents: list[str],
        top_k: int,
    ) -> list[RerankResult]:
        """via  LiteLLM Call rerank API"""
        try:
            import litellm
        except ImportError as e:
            raise ImportError("litellm is required for CloudReranker. Install with: uv add litellm") from e

        try:
            response = cast(
                "RerankResponse",
                await litellm.arerank(
                    model=self._model,
                    query=query,
                    documents=list(documents),
                    top_n=top_k,
                    api_key=self._api_key,
                    api_base=self._api_base,
                ),
            )
        except Exception as e:
            logger.warning(f"Failed to call LiteLLM rerank for model {self._model}: {type(e).__name__}: {e}")
            raise

        if not response.results:
            logger.warning(f"LiteLLM rerank returned empty results for model {self._model}")
            return []

        try:
            return [
                RerankResult(
                    index=item["index"],
                    score=item["relevance_score"],
                    text=documents[item["index"]],
                )
                for item in response.results
            ]
        except (KeyError, IndexError, TypeError) as e:
            error_msg = f"Unexpected response format from LiteLLM rerank: {type(e).__name__}: {e}"
            logger.warning(error_msg)
            raise ValueError(error_msg) from e
