"""FAQ hit tracking for analytics and unmatched query discovery.

[INPUT]
- app.database.models.faq::FaqHitLog (POS: ORM model)
- app.database.connection::get_session (POS: DB session)

[OUTPUT]
- FaqHitTracker: async fire-and-forget hit logger

[POS]
Records every FAQ match attempt (hit or miss) for analytics dashboards
and unmatched query discovery.
"""

from __future__ import annotations

import logging

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.connection import get_session
from app.database.models.faq import FaqHitLog

logger = logging.getLogger(__name__)


class FaqHitTracker:
    """Fire-and-forget FAQ hit/miss logger."""

    async def record(
        self,
        corpus_id: str,
        channel: str,
        user_query: str,
        top_score: float,
        *,
        entry_id: str | None = None,
        hit: bool = False,
    ) -> None:
        try:
            async with get_session() as session:
                log = FaqHitLog(
                    corpus_id=corpus_id,
                    entry_id=entry_id,
                    channel=channel,
                    user_query=user_query,
                    top_score=top_score,
                    hit=hit,
                )
                session.add(log)
                await session.commit()
        except Exception:
            logger.warning("Failed to record FAQ hit log", exc_info=True)

    async def get_stats(
        self,
        corpus_id: str,
        *,
        db: AsyncSession | None = None,
    ) -> dict[str, int]:
        """Return {total, hits, misses} counts for the corpus."""

        async def _query(session: AsyncSession) -> dict[str, int]:
            total_q = await session.execute(
                select(func.count()).where(FaqHitLog.corpus_id == corpus_id)
            )
            total = total_q.scalar() or 0

            hits_q = await session.execute(
                select(func.count()).where(
                    FaqHitLog.corpus_id == corpus_id,
                    FaqHitLog.hit.is_(True),
                )
            )
            hits = hits_q.scalar() or 0

            return {"total": total, "hits": hits, "misses": total - hits}

        if db is not None:
            return await _query(db)
        async with get_session() as session:
            return await _query(session)

    async def list_unmatched(
        self,
        corpus_id: str,
        *,
        limit: int = 50,
    ) -> list[dict[str, object]]:
        """Return recent unmatched queries for FAQ candidate discovery."""
        async with get_session() as session:
            result = await session.execute(
                select(FaqHitLog.user_query, FaqHitLog.top_score, FaqHitLog.created_at)
                .where(
                    FaqHitLog.corpus_id == corpus_id,
                    FaqHitLog.hit.is_(False),
                )
                .order_by(FaqHitLog.created_at.desc())
                .limit(limit)
            )
            return [
                {"query": row.user_query, "top_score": row.top_score, "time": row.created_at.isoformat()}
                for row in result
            ]
