"""[INPUT]
- .common (POS: shared constants)

[OUTPUT]
- MessagesMixin

[POS]
ChatRepository mixin: message CRUD, pagination, FTS search, extra-data read/write and FTS chat resolution.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.database.dto import MessageDTO
from app.database.models import Message
from app.database.models.chat import NOT_WAKEUP_NOTICE, WAKEUP_NOTICE_INERT_KINDS, WAKEUP_NOTICE_KIND
from app.database.repositories.chat_message_search_repo import ChatMessageSearchRepository, MessageFtsSearchRow

from .common import (
    _DTO_COMPUTED_FIELDS,
    logger,
)
from .siblings import SiblingsMixin


class MessagesMixin:
    @staticmethod
    async def count_messages(db: AsyncSession, chat_id: str) -> int:
        result = await db.execute(select(func.count()).select_from(Message).where(Message.chat_id == chat_id))
        return int(result.scalar_one())

    @staticmethod
    async def update_message_extra_data(db: AsyncSession, message_id: str, extra_data: dict[str, object]) -> None:
        if not extra_data:
            return
        await db.execute(update(Message).where(Message.id == message_id).values(extra_data=extra_data))

    @staticmethod
    async def add_message(db: AsyncSession, message: MessageDTO) -> None:
        db_msg = Message(**message.model_dump(exclude=_DTO_COMPUTED_FIELDS))
        db.add(db_msg)

    @staticmethod
    async def add_messages(db: AsyncSession, messages: list[MessageDTO]) -> None:
        db_msgs = [Message(**m.model_dump(exclude=_DTO_COMPUTED_FIELDS)) for m in messages]
        db.add_all(db_msgs)

    @staticmethod
    async def delete_all_messages_for_chat(db: AsyncSession, chat_id: str) -> None:
        await db.execute(delete(Message).where(Message.chat_id == chat_id))

    @staticmethod
    async def soft_delete_all_messages_for_chat(db: AsyncSession, chat_id: str) -> None:
        await db.execute(update(Message).where(Message.chat_id == chat_id).values(is_active=False))

    @staticmethod
    async def delete_messages_matching(db: AsyncSession, chat_id: str, condition: ColumnElement[bool]) -> list[MessageDTO]:
        result = await db.execute(select(Message).where(Message.chat_id == chat_id, condition))
        msgs = list(result.scalars().all())
        for msg in msgs:
            await db.delete(msg)
        return [MessageDTO.model_validate(m) for m in msgs]

    @staticmethod
    async def get_messages_paginated(
        db: AsyncSession, chat_id: str, cursor_id: str | None = None, limit: int = 10
    ) -> list[MessageDTO]:
        query = select(Message).where(Message.chat_id == chat_id, Message.is_active)
        if cursor_id:
            cursor_result = await db.execute(select(Message.created_at, Message.id).where(Message.id == cursor_id))
            cursor_row = cursor_result.one_or_none()
            if cursor_row:
                cursor_ts, c_id = cursor_row
                query = query.where((Message.created_at < cursor_ts) | ((Message.created_at == cursor_ts) & (Message.id < c_id)))
        result = await db.execute(query.order_by(Message.created_at.desc(), Message.id.desc()).limit(limit))
        msgs = result.scalars().all()
        dtos = [MessageDTO.model_validate(m) for m in msgs]

        group_ids = {d.sibling_group_id for d in dtos if d.sibling_group_id}
        if group_ids:
            sibling_counts = await SiblingsMixin._batch_sibling_counts(db, group_ids)
            for d in dtos:
                if d.sibling_group_id and d.sibling_group_id in sibling_counts:
                    info = sibling_counts[d.sibling_group_id]
                    d.sibling_count = info.total
                    d.sibling_index = info.ids.index(d.id) + 1 if d.id in info.ids else 0
        return dtos

    @staticmethod
    async def get_all_messages(db: AsyncSession, chat_id: str) -> list[MessageDTO]:
        result = await db.execute(
            select(Message)
            .where(Message.chat_id == chat_id, Message.is_active == True)  # noqa: E712
            .order_by(Message.created_at.asc(), Message.id.asc())
        )
        msgs = result.scalars().all()
        return [MessageDTO.model_validate(m) for m in msgs]

    @staticmethod
    async def get_assistant_extra_data(db: AsyncSession, chat_id: str) -> tuple[list[dict[str, object] | None], str | None]:
        """Load active assistant message extra_data and the last message id.

        Used for rebuilding the Chat.total_* usage cache. Skips the message
        content column so the aggregation stays cheap even for long sessions.
        The returned last_message_id identifies the newest active assistant
        message so the TTL cache can detect new messages / sibling switches.
        """
        result = await db.execute(
            select(Message.extra_data, Message.id)
            .where(
                Message.chat_id == chat_id,
                Message.role == "assistant",
                Message.is_active == True,  # noqa: E712
                Message.extra_data.isnot(None),
            )
            .order_by(Message.created_at.asc(), Message.id.asc())
        )
        rows = result.all()
        extras = [row[0] for row in rows]
        last_message_id = rows[-1][1] if rows else None
        return extras, last_message_id

    @staticmethod
    async def search_messages_fts(
        db: AsyncSession,
        safe_query: str,
        limit: int,
        offset: int,
        since: datetime | None,
        until: datetime | None,
    ) -> tuple[list[MessageFtsSearchRow], int]:
        return await ChatMessageSearchRepository.search_messages_fts(
            db,
            safe_query,
            limit,
            offset,
            since,
            until,
        )

    @staticmethod
    async def get_last_user_message(db: AsyncSession, chat_id: str) -> MessageDTO | None:
        """The latest row a person (or a wake turn's followup notice) opened a turn with.

        A settlement the wake router degraded or suppressed starts no turn, so its notice row is skipped: retry,
        regenerate and undo act on the turn before it.
        """
        result = await db.execute(
            select(Message)
            .where(
                Message.chat_id == chat_id,
                Message.role == "user",
                or_(NOT_WAKEUP_NOTICE, WAKEUP_NOTICE_KIND.not_in(WAKEUP_NOTICE_INERT_KINDS)),
            )
            .order_by(Message.created_at.desc(), Message.id.desc())
            .limit(1)
        )
        msg = result.scalar_one_or_none()
        return MessageDTO.model_validate(msg) if msg else None

    @staticmethod
    async def delete_messages_after(
        db: AsyncSession,
        chat_id: str,
        anchor: MessageDTO,
        include_anchor: bool = False,
    ) -> list[str]:
        """Delete messages after anchor and return their IDs."""
        if include_anchor:
            condition = (Message.created_at > anchor.created_at) | (
                (Message.created_at == anchor.created_at) & (Message.id >= anchor.id)
            )
        else:
            condition = (Message.created_at > anchor.created_at) | (
                (Message.created_at == anchor.created_at) & (Message.id > anchor.id)
            )
        to_delete = (await db.execute(select(Message).where(Message.chat_id == chat_id, condition))).scalars().all()
        deleted_ids = [msg.id for msg in to_delete]
        for msg in to_delete:
            await db.delete(msg)
        return deleted_ids

    @staticmethod
    async def get_latest_message(db: AsyncSession, chat_id: str, *, conversation_only: bool = False) -> MessageDTO | None:
        """The newest row of a chat; ``conversation_only`` leaves out the system's notes about settled background tasks."""
        query = select(Message).where(Message.chat_id == chat_id)
        if conversation_only:
            query = query.where(NOT_WAKEUP_NOTICE)
        result = await db.execute(query.order_by(Message.created_at.desc(), Message.id.desc()).limit(1))
        msg = result.scalar_one_or_none()
        return MessageDTO.model_validate(msg) if msg else None

    @staticmethod
    async def get_message_by_id(db: AsyncSession, chat_id: str, message_id: str) -> MessageDTO | None:
        result = await db.execute(select(Message).where(Message.chat_id == chat_id, Message.id == message_id))
        msg = result.scalar_one_or_none()
        return MessageDTO.model_validate(msg) if msg else None

    @staticmethod
    async def get_message_created_at(db: AsyncSession, message_id: str) -> datetime | None:
        result = await db.execute(select(Message.created_at).where(Message.id == message_id))
        value = result.scalar_one_or_none()
        return value if isinstance(value, datetime) else None

    @staticmethod
    async def get_recent_messages(
        db: AsyncSession,
        chat_id: str,
        limit: int = 50,
        exclude_message_id: str | None = None,
        after_ts: datetime | None = None,
    ) -> list[MessageDTO]:
        query = select(Message).where(Message.chat_id == chat_id, Message.is_active)
        if exclude_message_id:
            query = query.where(Message.id != exclude_message_id)
        if after_ts:
            query = query.where(Message.created_at > after_ts)

        result = await db.execute(query.order_by(Message.created_at.desc()).limit(limit))
        msgs = list(reversed(result.scalars().all()))
        dtos = [MessageDTO.model_validate(m) for m in msgs]

        group_ids = {d.sibling_group_id for d in dtos if d.sibling_group_id}
        if group_ids:
            sibling_counts = await SiblingsMixin._batch_sibling_counts(db, group_ids)
            for d in dtos:
                if d.sibling_group_id and d.sibling_group_id in sibling_counts:
                    info = sibling_counts[d.sibling_group_id]
                    d.sibling_count = info.total
                    d.sibling_index = info.ids.index(d.id) + 1 if d.id in info.ids else 0
        return dtos

    @staticmethod
    async def _fts_matching_chat_ids(db: AsyncSession, keyword: str) -> list[str]:
        """Best-effort FTS5 lookup for sidebar keyword search; returns [] on failure."""
        try:
            from myrm_agent_harness.utils.db.fts5 import sanitize_fts5_query

            safe_query = sanitize_fts5_query(keyword)
            if not safe_query:
                return []
            return await ChatMessageSearchRepository.get_matching_chat_ids(db, safe_query)
        except Exception:
            logger.debug("FTS sidebar search fallback to ilike-only for keyword=%r", keyword, exc_info=True)
            return []
