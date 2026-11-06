"""[INPUT]
- .common (POS: shared constants)

[OUTPUT]
- ChatsMixin

[POS]
ChatRepository mixin: chat list/detail, create/update, pins, trash lifecycle and compaction CAS.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast

from sqlalchemy import String as SQLString
from sqlalchemy import and_, case, delete, exists, func, or_, select, update
from sqlalchemy import cast as sql_cast
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.sql.elements import ColumnElement

from app.database.dto import ChatDTO
from app.database.models import Chat, Message

from .common import (
    _INCOGNITO_BLANKED_FIELDS,
)
from .messages import MessagesMixin


class ChatsMixin:
    @staticmethod
    async def get_chats_paginated(
        db: AsyncSession,
        offset: int,
        limit: int,
        source: str | None = None,
        project_id: str | None = None,
        unassigned: bool = False,
        keyword: str | None = None,
        tags: list[str] | None = None,
        match_mode: str = "any",
    ) -> tuple[list[ChatDTO], int]:
        where_clause: list[ColumnElement[bool]] = [Chat.deleted_at.is_(None), Chat.is_incognito.is_(False)]
        if source:
            where_clause.append(Chat.source == source)
        if project_id:
            where_clause.append(Chat.project_id == project_id)
        elif unassigned:
            where_clause.append(Chat.project_id.is_(None))
        if keyword:
            escaped = keyword.replace("%", r"\%").replace("_", r"\_")
            pattern = f"%{escaped}%"
            ilike_cond = or_(
                Chat.title.ilike(pattern, escape="\\"),
                Chat.first_message.ilike(pattern, escape="\\"),
            )
            fts_chat_ids = await MessagesMixin._fts_matching_chat_ids(db, keyword)
            if fts_chat_ids:
                where_clause.append(or_(ilike_cond, Chat.id.in_(fts_chat_ids)))
            else:
                where_clause.append(ilike_cond)
        if tags:
            clean_tags = [t.strip().lstrip("#") for t in tags if t.strip()]
            if clean_tags:
                tag_conds = [sql_cast(Chat.tags, SQLString).ilike(f'%"{t}"%') for t in clean_tags]
                if match_mode.lower() == "all":
                    where_clause.append(and_(*tag_conds))
                else:
                    where_clause.append(or_(*tag_conds))

        count_stmt = select(func.count(Chat.id)).where(*where_clause)
        count_result = await db.execute(count_stmt)
        total = count_result.scalar_one()

        query_stmt = (
            select(Chat)
            .where(*where_clause)
            .order_by(Chat.is_pinned.desc(), Chat.pin_order.asc(), Chat.updated_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await db.execute(query_stmt)
        chats = result.scalars().all()
        return [ChatDTO.model_validate(c) for c in chats], total

    @staticmethod
    async def update_chat_tags(db: AsyncSession, chat_id: str, tags: list[str]) -> list[str]:
        clean_tags = list(dict.fromkeys(t.strip().lstrip("#") for t in tags if t.strip()))
        await db.execute(update(Chat).where(Chat.id == chat_id).values(tags=clean_tags))
        return clean_tags

    @staticmethod
    async def get_chat_by_id(
        db: AsyncSession, chat_id: str, load_messages: bool = False, *, include_trashed: bool = False
    ) -> ChatDTO | None:
        stmt = select(Chat).where(Chat.id == chat_id)
        if not include_trashed:
            stmt = stmt.where(Chat.deleted_at.is_(None))
        if load_messages:
            stmt = stmt.options(selectinload(Chat.messages))
        result = await db.execute(stmt)
        chat = result.scalar_one_or_none()
        return ChatDTO.model_validate(chat) if chat else None

    @staticmethod
    async def add_chat(db: AsyncSession, chat: Chat | ChatDTO) -> None:
        # Convert DTO back to ORM model for insertion if necessary
        if isinstance(chat, ChatDTO):
            db_chat = Chat(**chat.model_dump(exclude={"messages"}))
        else:
            db_chat = chat
        if db_chat.is_incognito:
            for column in _INCOGNITO_BLANKED_FIELDS:
                setattr(db_chat, column, None)
        db.add(db_chat)

    @staticmethod
    async def update_chat_fields(db: AsyncSession, chat_id: str, updates: dict[str, object]) -> None:
        """Apply column updates; the preview columns of an incognito chat keep their (empty) value.

        The check runs inside the UPDATE statement against the stored row, so it costs no extra round trip.
        """
        if not updates:
            return
        values = {
            column: case((Chat.is_incognito.is_(True), Chat.__table__.c[column]), else_=value)
            if column in _INCOGNITO_BLANKED_FIELDS
            else value
            for column, value in updates.items()
        }
        await db.execute(update(Chat).where(Chat.id == chat_id).values(**values))

    @staticmethod
    async def cas_update_compaction(
        db: AsyncSession,
        chat_id: str,
        old_before_id: str | None,
        new_summary: str,
        new_before_id: str,
    ) -> bool:
        """Optimistic Concurrency Control (CAS) update for compacted summary."""
        stmt = update(Chat).where(Chat.id == chat_id)
        if old_before_id is None:
            stmt = stmt.where(Chat.compacted_before_id.is_(None))
        else:
            stmt = stmt.where(Chat.compacted_before_id == old_before_id)

        stmt = stmt.values(
            compacted_summary=new_summary,
            compacted_before_id=new_before_id,
            compacted_at=datetime.now(UTC),
        )

        result = cast(CursorResult[tuple[object, ...]], await db.execute(stmt))
        return bool(result.rowcount and result.rowcount > 0)

    @staticmethod
    async def get_channel_chat_by_key(db: AsyncSession, channel_session_key: str) -> ChatDTO | None:
        result = await db.execute(select(Chat).where(Chat.channel_session_key == channel_session_key))
        chat = result.scalar_one_or_none()
        return ChatDTO.model_validate(chat) if chat else None

    @staticmethod
    async def count_pinned(db: AsyncSession) -> int:
        result = await db.execute(
            select(func.count(Chat.id)).where(Chat.is_pinned == True)  # noqa: E712
        )
        return result.scalar_one()

    @staticmethod
    async def get_next_pin_order(db: AsyncSession) -> int:
        result = await db.execute(
            select(func.coalesce(func.max(Chat.pin_order), 0)).where(
                Chat.is_pinned == True  # noqa: E712
            )
        )
        return result.scalar_one() + 1

    @staticmethod
    async def pin_chat(db: AsyncSession, chat_id: str, pin_order: int) -> None:
        await db.execute(update(Chat).where(Chat.id == chat_id).values(is_pinned=True, pin_order=pin_order))

    @staticmethod
    async def unpin_chat(db: AsyncSession, chat_id: str) -> None:
        await db.execute(update(Chat).where(Chat.id == chat_id).values(is_pinned=False, pin_order=0))

    @staticmethod
    async def reorder_pinned_chats(db: AsyncSession, items: list[tuple[str, int]]) -> None:
        for chat_id, order in items:
            await db.execute(
                update(Chat)
                .where(Chat.id == chat_id, Chat.is_pinned == True)  # noqa: E712
                .values(pin_order=order)
            )

    @staticmethod
    async def soft_delete_chat(db: AsyncSession, chat_id: str) -> bool:
        result = cast(
            CursorResult[tuple[object, ...]],
            await db.execute(
                update(Chat)
                .where(Chat.id == chat_id, Chat.deleted_at.is_(None))
                .values(deleted_at=func.now(), is_pinned=False, pin_order=0)
            ),
        )
        return bool(result.rowcount and result.rowcount > 0)

    @staticmethod
    async def restore_chat(db: AsyncSession, chat_id: str) -> bool:
        result = cast(
            CursorResult[tuple[object, ...]],
            await db.execute(update(Chat).where(Chat.id == chat_id, Chat.deleted_at.isnot(None)).values(deleted_at=None)),
        )
        return bool(result.rowcount and result.rowcount > 0)

    @staticmethod
    async def get_trashed_chats_paginated(db: AsyncSession, offset: int, limit: int) -> tuple[list[ChatDTO], int]:
        where_clause = Chat.deleted_at.isnot(None)

        count_result = await db.execute(select(func.count(Chat.id)).where(where_clause))
        total = count_result.scalar_one()

        result = await db.execute(select(Chat).where(where_clause).order_by(Chat.deleted_at.desc()).offset(offset).limit(limit))
        chats = result.scalars().all()
        return [ChatDTO.model_validate(c) for c in chats], total

    @staticmethod
    async def count_trashed(db: AsyncSession) -> int:
        result = await db.execute(select(func.count(Chat.id)).where(Chat.deleted_at.isnot(None)))
        return result.scalar_one()

    @staticmethod
    async def permanently_delete_chat(db: AsyncSession, chat_id: str) -> bool:
        # 显式先删除关联的 messages，确保 SQLite messages_fts_delete 触发器正常执行，
        # 杜绝外键级联绕过子表触发器导致 FTS5 倒排索引残留孤儿行。
        # 仅当会话在回收站中才删消息：过期的回收站视图不能清空已被恢复的会话。
        # 单条带 EXISTS 的 DELETE 而非先 SELECT，避免读事务阻止写事务升级为 BEGIN IMMEDIATE。
        in_trash = exists().where(Chat.id == chat_id, Chat.deleted_at.isnot(None))
        await db.execute(delete(Message).where(Message.chat_id == chat_id, in_trash))
        result = cast(
            CursorResult[tuple[object, ...]],
            await db.execute(delete(Chat).where(Chat.id == chat_id, Chat.deleted_at.isnot(None))),
        )
        return bool(result.rowcount and result.rowcount > 0)

    @staticmethod
    async def empty_trash(db: AsyncSession) -> int:
        # 获取所有回收站会话 ID，先显式删除其所有 messages 触发 FTS5 倒排索引同步清理
        trashed_ids_result = await db.execute(select(Chat.id).where(Chat.deleted_at.isnot(None)))
        trashed_ids = [row[0] for row in trashed_ids_result.all()]
        if trashed_ids:
            await db.execute(delete(Message).where(Message.chat_id.in_(trashed_ids)))
        result = cast(
            CursorResult[tuple[object, ...]],
            await db.execute(delete(Chat).where(Chat.deleted_at.isnot(None))),
        )
        return result.rowcount or 0

    @staticmethod
    async def get_expired_trashed_chat_ids(db: AsyncSession, before: datetime) -> list[str]:
        result = await db.execute(select(Chat.id).where(Chat.deleted_at.isnot(None), Chat.deleted_at < before))
        return [row[0] for row in result.all()]
