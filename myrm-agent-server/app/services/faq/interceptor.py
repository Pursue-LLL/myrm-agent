"""FAQ semantic interceptor — zero-LLM fast path for channel messages.

[INPUT]
- app.database.models.faq::FaqCorpus, FaqEntry (POS: FAQ 语义缓存域模型)
- app.database.connection::get_session (POS: DB session)
- app.services.faq.corpus::_collection_name (POS: Qdrant collection 命名)
- myrm_agent_harness.toolkits.retriever.embedding.base::EmbeddingService (POS: embedding ABC)
- myrm_agent_harness.toolkits.vector.base::VectorStore (POS: vector store 抽象)

[OUTPUT]
- FaqMatchResult: semantic match result dataclass
- FaqInterceptor: stateless interceptor entry-point

[POS]
Intercepts inbound channel queries before agent execution. If a high-confidence
semantic match is found in the agent's FAQ corpus, returns the cached answer
directly, bypassing the full agent pipeline.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy import select

from app.database.connection import get_session
from app.database.models.faq import FaqCorpus, FaqEntry

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.retriever.embedding.base import EmbeddingService
    from myrm_agent_harness.toolkits.vector.base import VectorStore

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class FaqMatchResult:
    """Result of a successful FAQ match."""

    entry_id: str
    corpus_id: str
    question: str
    answer: str
    score: float
    score_gap: float


class FaqInterceptor:
    """Zero-LLM FAQ semantic interceptor for channel messages."""

    def __init__(
        self,
        embedding_service: "EmbeddingService",
        vector_store: "VectorStore",
    ) -> None:
        self._embedding = embedding_service
        self._vector = vector_store

    async def try_match(
        self,
        agent_id: str,
        user_query: str,
        *,
        channel: str = "web",
    ) -> tuple[FaqMatchResult | None, str | None, float]:
        """Try to match user_query against the agent's FAQ corpus.

        Returns (match_result, corpus_id, top_score):
        - match_result: FaqMatchResult if confident match, else None
        - corpus_id: corpus ID (for miss tracking), None if no corpus
        - top_score: highest similarity score seen (0.0 if no search performed)
        """
        stripped = user_query.strip()
        if not stripped or len(stripped) > 500:
            return None, None, 0.0

        corpus = await self._load_corpus(agent_id)
        if corpus is None or not corpus.enabled:
            return None, None, 0.0

        from app.services.faq.corpus import _collection_name

        collection = _collection_name(agent_id)
        try:
            exists = await self._vector.collection_exists(collection)
        except Exception:
            logger.warning("FAQ vector check failed for agent=%s", agent_id)
            return None, corpus.id, 0.0

        if not exists:
            return None, corpus.id, 0.0

        query_vec = await self._embedding.embed(stripped)

        results = await self._vector.search(
            collection,
            query_vec,
            limit=2,
        )

        if not results:
            return None, corpus.id, 0.0

        top = results[0]
        if top.score < corpus.threshold:
            return None, corpus.id, top.score

        score_gap = top.score - results[1].score if len(results) > 1 else 1.0
        if score_gap < corpus.min_score_gap:
            logger.debug(
                "FAQ score gap too small: top=%.3f, gap=%.3f, min_gap=%.3f",
                top.score, score_gap, corpus.min_score_gap,
            )
            return None, corpus.id, top.score

        entry_id = top.document.metadata.get("entry_id", top.document.id)
        entry = await self._load_entry(str(entry_id))
        if entry is None:
            return None, corpus.id, top.score

        return FaqMatchResult(
            entry_id=entry.id,
            corpus_id=corpus.id,
            question=entry.question,
            answer=entry.answer,
            score=top.score,
            score_gap=score_gap,
        ), corpus.id, top.score

    async def _load_corpus(self, agent_id: str) -> FaqCorpus | None:
        async with get_session() as session:
            result = await session.execute(
                select(FaqCorpus).where(FaqCorpus.agent_id == agent_id)
            )
            return result.scalar_one_or_none()

    async def _load_entry(self, entry_id: str) -> FaqEntry | None:
        async with get_session() as session:
            result = await session.execute(
                select(FaqEntry).where(FaqEntry.id == entry_id)
            )
            return result.scalar_one_or_none()
