"""[INPUT]
- .answering::WikiAnsweringMixin (POS: 答案阶段)
- .loading::WikiLoadingMixin (POS: 加载阶段)
- .retrieval::WikiRetrievalMixin (POS: 检索阶段)
- wiki.core.config::WikiConfig / WikiQueryConfig (POS: Wiki 配置)
- wiki.retrieval.indexer::WikiIndexer (POS: FTS5 索引器)

[OUTPUT]
- WikiQueryEngine: 对外查询入口

[POS]
`wiki/retrieval/query/` 的编排层；组合三个阶段并暴露 `query()`。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from myrm_agent_harness.utils.logger_utils import get_agent_logger

from ...core.config import WikiConfig, WikiQueryConfig
from ...core.structure import WikiStructure
from ...core.types import QueryResult
from ...pipeline.cognitive_map import read_hot_context, read_log_context
from ..indexer import WikiIndexer
from .answering import WikiAnsweringMixin
from .base import SemanticSearchFn
from .loading import WikiLoadingMixin
from .retrieval import WikiRetrievalMixin

logger = get_agent_logger(__name__)

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel

    from ..asset_index import WikiAssetIndexer


class WikiQueryEngine(WikiRetrievalMixin, WikiLoadingMixin, WikiAnsweringMixin):
    """Query engine for LLM-Wiki knowledge base."""

    def __init__(
        self,
        llm: BaseChatModel,
        structure: WikiStructure,
        config: WikiConfig,
        query_config: WikiQueryConfig | None = None,
        search_fn: SemanticSearchFn | None = None,
        indexer: WikiIndexer | None = None,
    ):
        self._llm = llm
        self._structure = structure
        self._config = config
        self._query_config = query_config or WikiQueryConfig()
        self._search_fn = search_fn
        self._indexer = indexer or WikiIndexer(structure, config)
        self._asset_indexer: WikiAssetIndexer | None = None

    async def query(
        self,
        question: str,
        query_config: WikiQueryConfig | None = None,
    ) -> QueryResult:
        """
        Query the wiki and get an answer.

        Args:
            question: User's question
            query_config: Optional per-query config override (e.g. raw_claim mode)

        Returns:
            QueryResult with context and related articles
        """
        effective_query_config = query_config or self._query_config
        logger.info(f"Querying wiki: {question[:100]}")

        hot_context = read_hot_context(self._structure)
        log_context = read_log_context(self._structure)

        # Step 1: Search for related concepts
        search_result = await self._search_concepts(question, effective_query_config)
        related_articles = search_result.article_paths
        logger.info(f"Found {len(related_articles)} related articles")

        if not related_articles:
            asset_snippets = await self._search_asset_snippets(question)
            if asset_snippets:
                asset_lines = "\n".join(f"- {snippet.snippet} ({snippet.article_path})" for snippet in asset_snippets)
                answer = self._compose_answer(
                    hot_context,
                    log_context,
                    f"## Related images\n{asset_lines}",
                    question,
                )
                return QueryResult(
                    question=question,
                    answer=answer,
                    related_articles=[],
                    should_archive=False,
                    confidence_score=0.5,
                    source_snippets=asset_snippets,
                )
            if hot_context or log_context:
                return QueryResult(
                    question=question,
                    answer=self._compose_hot_only_answer(hot_context, log_context),
                    related_articles=[],
                    should_archive=False,
                    confidence_score=0.1,
                    refused=self._refused_verdict(0.1, effective_query_config.min_answer_confidence),
                )
            return QueryResult(
                question=question,
                answer="No relevant information found in wiki. Consider ingesting more documents.",
                related_articles=[],
                should_archive=False,
                confidence_score=0.0,
                refused=self._refused_verdict(0.0, effective_query_config.min_answer_confidence),
            )

        # Step 2: Load article context and extract citation snippets
        context, snippets = await self._load_articles_context(
            related_articles,
            search_result.index_matches,
            effective_query_config,
        )
        asset_snippets = await self._search_asset_snippets(question)
        if asset_snippets:
            snippets = [*snippets, *asset_snippets]
            asset_lines = "\n".join(f"- {snippet.snippet} ({snippet.article_path})" for snippet in asset_snippets)
            asset_block = f"## Related images\n{asset_lines}"
            context = f"{context}\n\n{asset_block}" if context else asset_block
        context = self._compose_answer(hot_context, log_context, context, question)

        confidence = self._derive_query_confidence(
            index_matches=search_result.index_matches,
            seeds=search_result.seeds,
            snippets=snippets,
            article_count=len(related_articles),
        )
        retrieval_trace = self._build_retrieval_trace(
            index_matches=search_result.index_matches,
            seeds=search_result.seeds,
            sidecar_directories=search_result.sidecar_directories,
            article_paths=related_articles,
        )
        should_archive = (
            effective_query_config.auto_enhance_enabled and confidence >= effective_query_config.min_query_quality_score
        )
        # Fail-closed refusal: an invalid threshold config refuses answering
        # instead of silently passing unvetted content through on a broken gate.
        refused = self._refused_verdict(confidence, effective_query_config.min_answer_confidence)

        return QueryResult(
            question=question,
            answer=context,
            related_articles=[str(a) for a in related_articles],
            should_archive=should_archive,
            confidence_score=confidence,
            refused=refused,
            source_snippets=snippets,
            retrieval_trace=retrieval_trace,
        )
