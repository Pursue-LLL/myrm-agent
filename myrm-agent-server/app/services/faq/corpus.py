"""FAQ corpus CRUD and embedding index management.

[INPUT]
- app.database.models.faq::FaqCorpus, FaqEntry (POS: FAQ 语义缓存域模型)
- app.database.connection::get_session (POS: DB session)
- myrm_agent_harness.toolkits.retriever.embedding.base::EmbeddingService (POS: embedding ABC)
- myrm_agent_harness.toolkits.vector.base::VectorStore (POS: vector store 抽象)

[OUTPUT]
- FaqCorpusService: FAQ corpus CRUD + embedding index rebuild

[POS]
Business-layer FAQ corpus management. Provides CRUD for per-agent FAQ Q&A pairs
and synchronizes the Qdrant embedding index when entries change.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from nanoid import generate as nanoid
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.connection import get_session
from app.database.models.faq import FaqCorpus, FaqEntry

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.retriever.embedding.base import EmbeddingService
    from myrm_agent_harness.toolkits.vector.base import VectorStore

logger = logging.getLogger(__name__)

FAQ_COLLECTION_PREFIX = "faq_"
MIN_THRESHOLD = 0.75
MAX_THRESHOLD = 1.0


def _collection_name(agent_id: str) -> str:
    return f"{FAQ_COLLECTION_PREFIX}{agent_id}"


class FaqCorpusService:
    """Manages per-agent FAQ corpus CRUD and vector index sync."""

    async def get_or_create_corpus(self, agent_id: str, db: AsyncSession | None = None) -> FaqCorpus:
        async def _inner(session: AsyncSession) -> FaqCorpus:
            result = await session.execute(select(FaqCorpus).where(FaqCorpus.agent_id == agent_id))
            corpus = result.scalar_one_or_none()
            if corpus is not None:
                return corpus
            corpus = FaqCorpus(id=nanoid(size=16), agent_id=agent_id)
            session.add(corpus)
            await session.commit()
            await session.refresh(corpus)
            return corpus

        if db is not None:
            return await _inner(db)
        async with get_session() as session:
            return await _inner(session)

    async def list_entries(self, agent_id: str) -> list[FaqEntry]:
        async with get_session() as session:
            result = await session.execute(
                select(FaqEntry)
                .join(FaqCorpus)
                .where(FaqCorpus.agent_id == agent_id)
                .order_by(FaqEntry.sort_order, FaqEntry.created_at)
            )
            return list(result.scalars().all())

    async def add_entry(
        self,
        agent_id: str,
        question: str,
        answer: str,
        tags: str = "",
    ) -> FaqEntry:
        async with get_session() as session:
            corpus = await self.get_or_create_corpus(agent_id, db=session)
            entry = FaqEntry(
                id=nanoid(size=16),
                corpus_id=corpus.id,
                question=question.strip(),
                answer=answer.strip(),
                tags=tags.strip(),
            )
            session.add(entry)
            await session.commit()
            await session.refresh(entry)
            return entry

    async def update_entry(
        self,
        entry_id: str,
        *,
        question: str | None = None,
        answer: str | None = None,
        tags: str | None = None,
    ) -> FaqEntry | None:
        async with get_session() as session:
            result = await session.execute(select(FaqEntry).where(FaqEntry.id == entry_id))
            entry = result.scalar_one_or_none()
            if entry is None:
                return None
            if question is not None:
                entry.question = question.strip()
            if answer is not None:
                entry.answer = answer.strip()
            if tags is not None:
                entry.tags = tags.strip()
            await session.commit()
            await session.refresh(entry)
            return entry

    async def delete_entry(self, entry_id: str) -> bool:
        async with get_session() as session:
            result = await session.execute(delete(FaqEntry).where(FaqEntry.id == entry_id))
            await session.commit()
            return result.rowcount > 0  # type: ignore[union-attr]

    async def update_corpus_settings(
        self,
        agent_id: str,
        *,
        enabled: bool | None = None,
        threshold: float | None = None,
        min_score_gap: float | None = None,
    ) -> FaqCorpus:
        async with get_session() as session:
            corpus = await self.get_or_create_corpus(agent_id, db=session)
            if enabled is not None:
                corpus.enabled = enabled
            if threshold is not None:
                corpus.threshold = max(MIN_THRESHOLD, min(MAX_THRESHOLD, threshold))
            if min_score_gap is not None:
                corpus.min_score_gap = max(0.0, min(0.5, min_score_gap))
            await session.commit()
            await session.refresh(corpus)
            return corpus

    async def rebuild_index(
        self,
        agent_id: str,
        embedding_service: "EmbeddingService",
        vector_store: "VectorStore",
    ) -> int:
        """Rebuild the Qdrant index for all entries in the agent's FAQ corpus."""
        from myrm_agent_harness.toolkits.vector.base import VectorDocument

        entries = await self.list_entries(agent_id)
        if not entries:
            return 0

        collection = _collection_name(agent_id)
        try:
            await vector_store.delete_collection(collection)
        except Exception:
            pass

        await vector_store.create_collection(
            collection,
            dimension=embedding_service.dimension,
        )

        questions = [e.question for e in entries]
        embeddings = await embedding_service.embed_batch(questions)

        docs = [
            VectorDocument(
                id=entry.id,
                content=entry.question,
                vector=emb,
                metadata={"entry_id": entry.id},
            )
            for entry, emb in zip(entries, embeddings, strict=True)
        ]
        await vector_store.upsert(collection, docs)
        logger.info("FAQ index rebuilt for agent=%s, entries=%d", agent_id, len(docs))
        return len(docs)

    async def bulk_import(
        self,
        agent_id: str,
        items: list[dict[str, str]],
    ) -> int:
        """Import FAQ entries in bulk. Each item must have 'question' and 'answer' keys."""
        valid = [
            (item.get("question", "").strip(), item.get("answer", "").strip(), item.get("tags", "").strip())
            for item in items
            if item.get("question", "").strip() and item.get("answer", "").strip()
        ]
        if not valid:
            return 0

        async with get_session() as session:
            corpus = await self.get_or_create_corpus(agent_id, db=session)
            for q, a, tags in valid:
                session.add(
                    FaqEntry(
                        id=nanoid(size=16),
                        corpus_id=corpus.id,
                        question=q,
                        answer=a,
                        tags=tags,
                    )
                )
            await session.commit()
        return len(valid)
