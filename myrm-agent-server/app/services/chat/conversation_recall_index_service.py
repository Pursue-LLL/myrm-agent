"""Conversation Recall index lifecycle service.

[INPUT]
- app.database.repositories.conversation_recall_repo::ConversationRecallRepository (POS: Conversation Recall 索引仓储)
- app.database.repositories.uow::UnitOfWork (POS: 全局工作单元模式)
- sqlalchemy.ext.asyncio::AsyncSession (POS: async database session)

[OUTPUT]
- ConversationRecallIndexService: Server business service for recall index lifecycle and management queries.

[POS]
Conversation Recall 索引生命周期服务。统一编排索引回填、重建、增量追加、排除/恢复、删除、健康检查和前端管理列表。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.repositories.conversation_recall_repo import (
    ConversationRecallDocumentRow,
    ConversationRecallRepository,
)
from app.database.repositories.uow import UnitOfWork


class ConversationRecallIndexService:
    """Server-facing lifecycle boundary for Conversation Recall indexing."""

    @staticmethod
    async def bootstrap_missing(db: AsyncSession) -> None:
        await ConversationRecallRepository.bootstrap_missing(db)

    @staticmethod
    async def rebuild_chat(db: AsyncSession, chat_id: str) -> None:
        await ConversationRecallRepository.rebuild_chat(db, chat_id)

    @staticmethod
    async def append_message(
        db: AsyncSession,
        *,
        chat_id: str,
        message_id: str,
        role: str,
        content: str,
        sent_at: datetime,
    ) -> None:
        await ConversationRecallRepository.append_message(
            db,
            chat_id=chat_id,
            message_id=message_id,
            role=role,
            content=content,
            sent_at=sent_at,
        )

    @staticmethod
    async def delete_chat(db: AsyncSession, chat_id: str) -> None:
        await ConversationRecallRepository.delete_chat(db, chat_id)

    @staticmethod
    async def set_chat_excluded(chat_id: str, excluded: bool) -> bool:
        async with UnitOfWork() as uow:
            session = uow.session
            if session is None:
                return False
            return await ConversationRecallRepository.set_excluded(session, chat_id, excluded)

    @staticmethod
    async def list_documents(
        *,
        excluded: bool | None,
        page: int,
        page_size: int,
    ) -> tuple[list[ConversationRecallDocumentRow], int]:
        safe_page = max(page, 1)
        safe_page_size = min(max(page_size, 1), 100)
        offset = (safe_page - 1) * safe_page_size
        async with UnitOfWork() as uow:
            session = uow.session
            if session is None:
                return [], 0
            return await ConversationRecallRepository.list_documents(
                session,
                excluded=excluded,
                limit=safe_page_size,
                offset=offset,
            )

    @staticmethod
    async def health() -> dict[str, object]:
        async with UnitOfWork() as uow:
            session = uow.session
            if session is None:
                return {
                    "indexed_conversations": 0,
                    "indexed_segments": 0,
                    "excluded_conversations": 0,
                    "missing_conversations": 0,
                    "missing_segments": 0,
                    "fts_ready": False,
                    "segments_fts_ready": False,
                    "last_indexed_at": None,
                }
            health = await ConversationRecallRepository.health(session)
            return {
                "indexed_conversations": health.indexed_conversations,
                "indexed_segments": health.indexed_segments,
                "excluded_conversations": health.excluded_conversations,
                "missing_conversations": health.missing_conversations,
                "missing_segments": health.missing_segments,
                "fts_ready": health.fts_ready,
                "segments_fts_ready": health.segments_fts_ready,
                "last_indexed_at": health.last_indexed_at.isoformat() if health.last_indexed_at else None,
            }
