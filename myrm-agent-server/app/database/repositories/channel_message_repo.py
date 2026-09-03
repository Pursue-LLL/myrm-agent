"""
[INPUT] models.channel_message::ChannelMessageModel, sqlalchemy::AsyncSession
[OUTPUT] ChannelMessageRepository: 多渠道入站明细仓储层
[POS] 渠道数据平面（Channel Data Plane）持久化访问。提供极速单条追加、上下文拉取、知识学习候选集查询与 30 天冷热生命周期滚动修剪。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Sequence

from sqlalchemy import Integer, delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.channel_message import ChannelMessageModel


class ChannelMessageRepository:
    """Repository managing channel inbound message records."""

    @staticmethod
    async def record_message(
        session: AsyncSession,
        message: ChannelMessageModel,
    ) -> ChannelMessageModel:
        """Atomically persist a single redacted and tagged channel message with idempotent collision handling."""
        try:
            if hasattr(session, "begin_nested"):
                nested = session.begin_nested()
                if hasattr(nested, "__aenter__"):
                    async with nested:
                        session.add(message)
                        await session.flush()
                else:
                    session.add(message)
                    await session.flush()
            else:
                session.add(message)
                await session.flush()
        except IntegrityError:
            # Idempotently absorb duplicate message_id on webhook retries
            pass
        return message

    @staticmethod
    async def get_recent_context(
        session: AsyncSession,
        channel: str,
        chat_id: str,
        limit: int = 30,
    ) -> list[ChannelMessageModel]:
        """Fetch the most recent N messages for a chat, ordered chronologically (oldest to newest)."""
        stmt = (
            select(ChannelMessageModel)
            .where(
                ChannelMessageModel.channel == channel,
                ChannelMessageModel.chat_id == chat_id,
            )
            .order_by(ChannelMessageModel.created_at.desc())
            .limit(limit)
        )
        result = await session.execute(stmt)
        messages: Sequence[ChannelMessageModel] = result.scalars().all()
        # Return in ascending order for natural prompt turn reconstruction
        return list(reversed(messages))

    @staticmethod
    async def get_learning_candidates(
        session: AsyncSession,
        channel: str | None = None,
        since: datetime | None = None,
        limit: int = 100,
    ) -> list[ChannelMessageModel]:
        """Fetch messages eligible for knowledge extraction and background memory distillation."""
        stmt = select(ChannelMessageModel).where(
            ChannelMessageModel.learning_eligible.is_(True),
            ChannelMessageModel.is_self.is_(False),
        )
        if channel:
            stmt = stmt.where(ChannelMessageModel.channel == channel)
        if since:
            stmt = stmt.where(ChannelMessageModel.created_at >= since)

        stmt = stmt.order_by(ChannelMessageModel.created_at.asc()).limit(limit)
        result = await session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def prune_expired(
        session: AsyncSession,
        retention_days: int = 30,
    ) -> int:
        """Prune messages older than retention_days. Returns the number of pruned rows."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
        stmt = delete(ChannelMessageModel).where(
            ChannelMessageModel.created_at < cutoff
        )
        result = await session.execute(stmt)
        await session.flush()
        return int(result.rowcount or 0)

    @staticmethod
    async def get_channel_stats(
        session: AsyncSession,
        channel: str | None = None,
    ) -> dict[str, int]:
        """Get aggregate counts for channel data plane monitoring."""
        stmt = select(
            func.count(ChannelMessageModel.id),
            func.sum(func.cast(ChannelMessageModel.learning_eligible, Integer)),
            func.sum(func.cast(ChannelMessageModel.is_trigger, Integer)),
        )
        if channel:
            stmt = stmt.where(ChannelMessageModel.channel == channel)

        result = await session.execute(stmt)
        row = result.first()
        total_count = int(row[0] or 0) if row else 0
        learning_count = int(row[1] or 0) if row and row[1] is not None else 0
        trigger_count = int(row[2] or 0) if row and row[2] is not None else 0

        return {
            "total_messages": total_count,
            "learning_eligible": learning_count,
            "trigger_messages": trigger_count,
        }

    @staticmethod
    async def clear_chat_history(
        session: AsyncSession,
        channel: str,
        chat_id: str | None = None,
    ) -> int:
        """GDPR Right to be Forgotten: clear all ambient messages for a given channel/chat."""
        stmt = delete(ChannelMessageModel).where(ChannelMessageModel.channel == channel)
        if chat_id:
            stmt = stmt.where(ChannelMessageModel.chat_id == chat_id)
        result = await session.execute(stmt)
        await session.flush()
        return int(result.rowcount or 0)
