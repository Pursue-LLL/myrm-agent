"""Retrieval tools orchestrator.

[INPUT]
- retriever.embedding::EmbeddingService (POS: embedding module facade, embedding service abstraction)
- retriever.reranker::RerankerService (POS: reranker module facade, reranking interface abstraction)
- retriever.preprocessing::create_document_chunks_from_crawl_results (POS: document preprocessing, convert crawl results to document chunks)
- retriever.hybrid_retriever::hybrid_retriever (POS: stable public facade for hybrid retrieval)
- web_fetch::SuccessResult, FailedResult (POS: web crawl result types)
- core.context_vars::source_indexer_var (POS: the run's source numbering, so the numbers a result prints are the indexes of its cards)
- utils.context_format::format_documents_with_metadata (POS: document formatting utility)
- pydantic::BaseModel, ConfigDict, Field (POS: configuration validation)

[OUTPUT]
- RetrieverConfig: retrieval config class, unified management of retrieval parameters
- RetrieverManager: retrieval manager class, providing hybrid retrieval and reranking

[POS]
Hybrid retrieval manager for fetched pages. Chunk sets no larger than `hybrid_top_k_per_query` go
straight to the reranker; larger sets are first narrowed by BM25 + vector retrieval fused with RRF,
then reranked. Multi-query input is supported.
"""

from __future__ import annotations

import logging

from langchain_core.documents import Document
from pydantic import BaseModel, ConfigDict, Field

from myrm_agent_harness.core.context_vars import source_indexer_var
from myrm_agent_harness.toolkits.retriever.embedding import EmbeddingService
from myrm_agent_harness.toolkits.retriever.hybrid_retriever import hybrid_retriever
from myrm_agent_harness.toolkits.retriever.preprocessing import create_document_chunks_from_crawl_results
from myrm_agent_harness.toolkits.retriever.reranker import RerankerService
from myrm_agent_harness.toolkits.web_fetch import FailedResult, SuccessResult
from myrm_agent_harness.utils.context_format import format_documents_with_metadata

logger = logging.getLogger(__name__)


class RetrieverConfig(BaseModel):
    """Retrieval configuration (tunable per scenario, supports runtime adjustment).

    Fields:
    - hybrid_top_k_per_query: Docs returned per query in hybrid retrieval
    """

    model_config = ConfigDict()

    hybrid_top_k_per_query: int = Field(
        default=50, ge=10, le=200, description="Docs returned per query in hybrid retrieval"
    )


DEFAULT_RETRIEVER_CONFIG = RetrieverConfig()


class RetrieverManager:
    """Retrieval manager providing hybrid search and reranking

    Core methods:
    - retrieve_from_crawl_results: Retrieve from crawl results (auto-selects optimal strategy)
    - direct_reranking_only: Direct reranking (for small document sets)
    - hybrid_retrieval_with_reranking: Hybrid retrieval + reranking (for large document sets)
    - retrieve_from_urls: Crawl URLs and retrieve relevant content
    """

    def __init__(self, config: RetrieverConfig | None = None):
        # Deep copy to avoid race conditions from shared config
        self.config = (config or DEFAULT_RETRIEVER_CONFIG).model_copy(deep=True)

    async def retrieve_from_crawl_results(
        self,
        queries: str | list[str],
        reranker: RerankerService,
        embeddings: EmbeddingService,
        *,
        top_k: int = 10,
        pre_crawled_results: tuple[SuccessResult, FailedResult] = ([], []),
        hybrid_top_k_per_query: int | None = None,
        fusion_weights: tuple[float, float, float, float] | None = None,
        rerank_score_threshold: float = 0.0,
        fusion_score_threshold: float = 0.0,
    ) -> tuple[list[dict[str, object]], str]:
        """Retrieve relevant docs from crawl results and return formatted text (auto-selects optimal strategy).

        Strategy selection:
        - Chunks ≤ hybrid_top_k_per_query: direct reranking
        - Chunks > hybrid_top_k_per_query: hybrid retrieval (BM25 + vector) + reranking
        """
        hybrid_top_k_per_query = hybrid_top_k_per_query or self.config.hybrid_top_k_per_query
        fusion_weights = fusion_weights or (1.0, 0.0, 0.0, 0.0)

        success_results, _ = pre_crawled_results

        if not success_results:
            logger.warning("All URLs failed to crawl")
            return [], ""

        query_list = queries if isinstance(queries, list) else [queries]

        all_chunk_documents = await create_document_chunks_from_crawl_results(
            success_results,
            queries=query_list,
        )
        logger.info(f"Successfully created {len(all_chunk_documents)} document chunks")

        if not all_chunk_documents:
            return [], ""

        logger.info(f"Unified document pool: {len(all_chunk_documents)} chunks, {len(query_list)} queries")

        if len(all_chunk_documents) <= hybrid_top_k_per_query:
            logger.info(
                f"Document count ({len(all_chunk_documents)}) <= {hybrid_top_k_per_query}, using direct reranking"
            )
            relevant_docs = await hybrid_retriever.direct_reranking_only(
                queries=query_list,
                documents=all_chunk_documents,
                reranker=reranker,
                final_top_k=top_k,
                dedup_strategy="content",
                fusion_weights=fusion_weights,
                rerank_score_threshold=rerank_score_threshold,
                fusion_score_threshold=fusion_score_threshold,
            )
        else:
            logger.info(
                f"Document count ({len(all_chunk_documents)}) > {hybrid_top_k_per_query}, using hybrid retrieval + reranking"
            )
            relevant_docs = await hybrid_retriever.hybrid_retrieval_with_reranking(
                queries=query_list,
                documents=all_chunk_documents,
                reranker=reranker,
                embeddings=embeddings,
                final_top_k=top_k,
                hybrid_top_k_per_query=hybrid_top_k_per_query,
                dedup_strategy="content",
                fusion_weights=fusion_weights,
                rerank_score_threshold=rerank_score_threshold,
                fusion_score_threshold=fusion_score_threshold,
            )

        sources_metadata, formatted_context, _ = format_documents_with_metadata(
            relevant_docs,
            questions=query_list,
            index_for=source_indexer_var.get(),
        )
        return sources_metadata, formatted_context

    async def direct_reranking_only(
        self,
        queries: list[str],
        documents: list[Document],
        reranker: RerankerService,
        *,
        final_top_k: int = 10,
        dedup_strategy: str = "content",
        fusion_weights: tuple[float, float, float, float] = (1.0, 0.0, 0.0, 0.0),
        rerank_score_threshold: float = 0.6,
        fusion_score_threshold: float = 0.6,
    ) -> list[Document]:
        """Direct reranking entry point, skipping hybrid retrieval (for small document sets)."""
        return await hybrid_retriever.direct_reranking_only(
            queries=queries,
            documents=documents,
            reranker=reranker,
            final_top_k=final_top_k,
            dedup_strategy=dedup_strategy,
            fusion_weights=fusion_weights,
            rerank_score_threshold=rerank_score_threshold,
            fusion_score_threshold=fusion_score_threshold,
        )

    async def hybrid_retrieval_with_reranking(
        self,
        queries: list[str],
        documents: list[Document],
        reranker: RerankerService,
        embeddings: EmbeddingService,
        *,
        final_top_k: int = 10,
        hybrid_top_k_per_query: int = 20,
        dedup_strategy: str = "content",
        fusion_weights: tuple[float, float, float, float] = (1.0, 0.0, 0.0, 0.0),
        rerank_score_threshold: float = 0.0,
        fusion_score_threshold: float = 0.0,
    ) -> list[Document]:
        """Hybrid retrieval + reranking entry point."""
        return await hybrid_retriever.hybrid_retrieval_with_reranking(
            queries=queries,
            documents=documents,
            reranker=reranker,
            embeddings=embeddings,
            final_top_k=final_top_k,
            hybrid_top_k_per_query=hybrid_top_k_per_query,
            dedup_strategy=dedup_strategy,
            fusion_weights=fusion_weights,
            rerank_score_threshold=rerank_score_threshold,
            fusion_score_threshold=fusion_score_threshold,
        )

    async def retrieve_from_urls(
        self,
        urls: list[str],
        questions: str | list[str],
        reranker: RerankerService,
        embeddings: EmbeddingService,
        *,
        top_k: int = 10,
        use_raw_markdown: bool = False,
        allow_private_networks: bool = False,
    ) -> tuple[list[dict[str, object]], str, str | None]:
        """Crawl webpages and retrieve relevant content snippets

        Args:
            urls: Target webpage URL list
            questions: Retrieval queries (single string or list)
            reranker: Reranker service instance
            embeddings: Embedding service instance
            top_k: Maximum document chunks to return
            use_raw_markdown: Whether to use raw markdown format
            allow_private_networks: Skip SSRF private-IP blocking (local mode).

        Returns:
            (metadata list, formatted context, error info)
        """
        from myrm_agent_harness.toolkits.web_fetch import FetchEngine, web_fetch_tools

        if not urls:
            return [], "", "No URLs provided"

        if not questions:
            return [], "", "No queries provided"

        try:
            engine = FetchEngine(
                use_raw_markdown=use_raw_markdown,
                allow_private_networks=allow_private_networks,
                session_vault=web_fetch_tools._http_fetcher._session_vault,
            )
            success_results, failed_results = await engine.crawl_many(urls)

            if not success_results:
                error_msg = "All URLs failed to crawl"
                if failed_results:
                    failed_urls = [url for url, _ in failed_results]
                    error_msg = f"Failed to crawl URLs: {failed_urls}"
                return [], "", error_msg

            query_list = questions if isinstance(questions, list) else [questions]

            url_metadata_list, formatted_context = await self.retrieve_from_crawl_results(
                query_list,
                reranker,
                embeddings,
                top_k=top_k,
                pre_crawled_results=(success_results, failed_results),
            )

            return url_metadata_list, formatted_context, ""

        except Exception as e:
            error_msg = str(e).split("\n")[0][:200]
            logger.error(f"Retrieve from URLs failed: {error_msg}")
            return [], "", f"Retrieve from URLs failed: {e!s}"


__all__ = [
    "DEFAULT_RETRIEVER_CONFIG",
    "RetrieverConfig",
    "RetrieverManager",
]
