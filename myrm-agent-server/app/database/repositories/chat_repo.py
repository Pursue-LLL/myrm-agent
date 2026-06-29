"""Chat and message repository.

[INPUT]
app.database.models::Chat, Message (POS: 会话与消息域模型。管理聊天会话、消息记录和对话分支)
app.database.repositories.chat_message_search_repo::ChatMessageSearchRepository (POS: 聊天消息全文检索仓储。封装消息级 FTS5 查询，并复用 Conversation Recall 的排除策略)

[OUTPUT]
ChatRepository: Chat/Message CRUD, FTS5 message search, compaction CAS and sibling branch persistence.
SiblingDetail: Sibling branch query DTO.

[POS]
聊天领域数据仓储层。封装 Chat/Message 持久化、消息级检索委托和 sibling group 管理。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TypedDict, cast
from uuid import uuid4

from sqlalchemy import delete, desc, func, or_, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.sql.elements import ColumnElement

from app.database.dto import ChatDTO, MessageDTO
from app.database.models import Chat, Message
from app.database.repositories.chat_message_search_repo import ChatMessageSearchRepository, MessageFtsSearchRow


@dataclass
class _SiblingGroupInfo:
    total: int
    ids: list[str] = field(default_factory=list)


class SiblingDetail(TypedDict):
    id: str
    is_active: bool
    created_at: datetime


_DTO_COMPUTED_FIELDS: set[str] = {"sibling_count", "sibling_index"}


class ChatRepository:
    """
    Chat 领域的专有仓储类（Repository）。
    负责所有的 SQLAlchemy DB 交互，隔离上层服务（Service）与底层数据库结构的耦合。
    返回 Pydantic DTO (Domain Transfer Object) 以确保类型安全和解耦。
    """

    @staticmethod
    async def get_chats_paginated(
        db: AsyncSession,
        offset: int,
        limit: int,
        source: str | None = None,
        project_id: str | None = None,
        unassigned: bool = False,
        keyword: str | None = None,
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
            where_clause.append(
                or_(
                    Chat.title.ilike(pattern, escape="\\"),
                    Chat.first_message.ilike(pattern, escape="\\"),
                )
            )

        count_stmt = select(func.count(Chat.id)).where(*where_clause)
        count_result = await db.execute(count_stmt)
        total = count_result.scalar_one()

        query_stmt = (
            select(Chat)
            .where(*where_clause)
            .order_by(desc(Chat.is_pinned), Chat.pin_order.asc(), desc(Chat.updated_at))
            .offset(offset)
            .limit(limit)
        )
        result = await db.execute(query_stmt)
        chats = result.scalars().all()
        return [ChatDTO.model_validate(c) for c in chats], total

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
    async def count_messages(db: AsyncSession, chat_id: str) -> int:
        result = await db.execute(select(func.count()).select_from(Message).where(Message.chat_id == chat_id))
        return int(result.scalar_one())

    @staticmethod
    async def add_chat(db: AsyncSession, chat: Chat | ChatDTO) -> None:
        # Convert DTO back to ORM model for insertion if necessary
        if isinstance(chat, ChatDTO):
            db_chat = Chat(**chat.model_dump(exclude={"messages"}))
        else:
            db_chat = chat
        db.add(db_chat)

    @staticmethod
    async def update_chat_fields(db: AsyncSession, chat_id: str, updates: dict[str, object]) -> None:
        if not updates:
            return
        await db.execute(update(Chat).where(Chat.id == chat_id).values(**updates))

    @staticmethod
    async def update_message_extra_data(db: AsyncSession, message_id: str, extra_data: dict[str, object]) -> None:
        if not extra_data:
            return
        await db.execute(update(Message).where(Message.id == message_id).values(extra_data=extra_data))

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
            compacted_at=datetime.utcnow(),
        )

        result = cast(CursorResult[tuple[object, ...]], await db.execute(stmt))
        return bool(result.rowcount and result.rowcount > 0)

    @staticmethod
    async def get_channel_chat_by_key(db: AsyncSession, channel_session_key: str) -> ChatDTO | None:
        result = await db.execute(select(Chat).where(Chat.channel_session_key == channel_session_key))
        chat = result.scalar_one_or_none()
        return ChatDTO.model_validate(chat) if chat else None

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
            sibling_counts = await ChatRepository._batch_sibling_counts(db, group_ids)
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
        result = await db.execute(
            select(Message)
            .where(Message.chat_id == chat_id, Message.role == "user")
            .order_by(Message.created_at.desc(), Message.id.desc())
            .limit(1)
        )
        msg = result.scalar_one_or_none()
        return MessageDTO.model_validate(msg) if msg else None

    @staticmethod
    async def delete_messages_after(db: AsyncSession, chat_id: str, anchor: MessageDTO, include_anchor: bool = False) -> int:
        if include_anchor:
            condition = (Message.created_at > anchor.created_at) | (
                (Message.created_at == anchor.created_at) & (Message.id >= anchor.id)
            )
        else:
            condition = (Message.created_at > anchor.created_at) | (
                (Message.created_at == anchor.created_at) & (Message.id > anchor.id)
            )
        to_delete = (await db.execute(select(Message).where(Message.chat_id == chat_id, condition))).scalars().all()
        for msg in to_delete:
            await db.delete(msg)
        return len(to_delete)

    @staticmethod
    async def get_latest_message(db: AsyncSession, chat_id: str) -> MessageDTO | None:
        result = await db.execute(
            select(Message).where(Message.chat_id == chat_id).order_by(Message.created_at.desc(), Message.id.desc()).limit(1)
        )
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
            sibling_counts = await ChatRepository._batch_sibling_counts(db, group_ids)
            for d in dtos:
                if d.sibling_group_id and d.sibling_group_id in sibling_counts:
                    info = sibling_counts[d.sibling_group_id]
                    d.sibling_count = info.total
                    d.sibling_index = info.ids.index(d.id) + 1 if d.id in info.ids else 0
        return dtos

    @staticmethod
    async def _batch_sibling_counts(
        db: AsyncSession,
        group_ids: set[str],
    ) -> dict[str, _SiblingGroupInfo]:
        """Batch-fetch sibling counts and ordered ids for multiple groups."""
        result = await db.execute(
            select(Message.sibling_group_id, Message.id, Message.created_at)
            .where(Message.sibling_group_id.in_(group_ids))
            .order_by(Message.created_at.asc(), Message.id.asc())
        )
        groups: dict[str, _SiblingGroupInfo] = {}
        for row in result.all():
            gid = row.sibling_group_id
            if gid not in groups:
                groups[gid] = _SiblingGroupInfo(total=0, ids=[])
            groups[gid].total += 1
            groups[gid].ids.append(row.id)
        return groups

    @staticmethod
    async def deactivate_last_assistant_siblings(
        db: AsyncSession,
        chat_id: str,
        last_user_msg: MessageDTO,
    ) -> tuple[str, str]:
        """Mark the last assistant messages as inactive and return (query, sibling_group_id).

        Finds all assistant messages after the given user message, assigns them
        a shared sibling_group_id (reusing existing if present), and sets
        is_active=False.  Returns the user query and the sibling_group_id so
        the caller can attach the same group to the regenerated response.
        """
        condition = (Message.created_at > last_user_msg.created_at) | (
            (Message.created_at == last_user_msg.created_at) & (Message.id > last_user_msg.id)
        )
        result = await db.execute(
            select(Message).where(
                Message.chat_id == chat_id,
                condition,
                Message.role == "assistant",
            )
        )
        assistant_msgs = result.scalars().all()

        group_id = ""
        for m in assistant_msgs:
            if m.sibling_group_id:
                group_id = m.sibling_group_id
                break
        if not group_id:
            group_id = str(uuid4())

        for m in assistant_msgs:
            m.is_active = False
            m.sibling_group_id = group_id

        return last_user_msg.content, group_id

    @staticmethod
    async def switch_active_sibling(
        db: AsyncSession,
        sibling_group_id: str,
        target_message_id: str,
    ) -> bool:
        """Set the target message as active and all other siblings as inactive."""
        result = await db.execute(select(Message).where(Message.sibling_group_id == sibling_group_id))
        siblings = result.scalars().all()
        if not siblings:
            return False

        found = False
        for m in siblings:
            if m.id == target_message_id:
                m.is_active = True
                found = True
            else:
                m.is_active = False
        return found

    @staticmethod
    async def get_sibling_info(
        db: AsyncSession,
        sibling_group_id: str,
    ) -> list[SiblingDetail]:
        """Return ordered list of sibling message summaries for a group."""
        result = await db.execute(
            select(Message.id, Message.is_active, Message.created_at)
            .where(Message.sibling_group_id == sibling_group_id)
            .order_by(Message.created_at.asc(), Message.id.asc())
        )
        return [SiblingDetail(id=row.id, is_active=row.is_active, created_at=row.created_at) for row in result.all()]

    @staticmethod
    async def get_recent_routing_tiers(db: AsyncSession, chat_id: str, limit: int = 5) -> list[str]:
        """Fetch routing tiers from recent assistant messages for momentum calculation.

        Returns tier strings (e.g. ["STANDARD", "REASONING"]) in chronological order.
        Only returns tiers that were actually recorded (skips messages without routing data).
        """
        result = await db.execute(
            select(Message.extra_data)
            .where(
                Message.chat_id == chat_id,
                Message.role == "assistant",
                Message.extra_data.isnot(None),
            )
            .order_by(desc(Message.created_at))
            .limit(limit)
        )
        rows = result.scalars().all()
        tiers: list[str] = []
        for extra in reversed(rows):
            if isinstance(extra, dict):
                tier = extra.get("routingTier")
                if isinstance(tier, str):
                    tiers.append(tier)
        return tiers

    # ── Pinned Threads ──────────────────────────────────────────────

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

    # ── Trash (Soft-delete) ─────────────────────────────────────────

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

        result = await db.execute(select(Chat).where(where_clause).order_by(desc(Chat.deleted_at)).offset(offset).limit(limit))
        chats = result.scalars().all()
        return [ChatDTO.model_validate(c) for c in chats], total

    @staticmethod
    async def count_trashed(db: AsyncSession) -> int:
        result = await db.execute(select(func.count(Chat.id)).where(Chat.deleted_at.isnot(None)))
        return result.scalar_one()

    @staticmethod
    async def permanently_delete_chat(db: AsyncSession, chat_id: str) -> bool:
        result = cast(
            CursorResult[tuple[object, ...]],
            await db.execute(delete(Chat).where(Chat.id == chat_id, Chat.deleted_at.isnot(None))),
        )
        return bool(result.rowcount and result.rowcount > 0)

    @staticmethod
    async def empty_trash(db: AsyncSession) -> int:
        result = cast(
            CursorResult[tuple[object, ...]],
            await db.execute(delete(Chat).where(Chat.deleted_at.isnot(None))),
        )
        return result.rowcount or 0

    @staticmethod
    async def get_expired_trashed_chat_ids(db: AsyncSession, before: datetime) -> list[str]:
        result = await db.execute(select(Chat.id).where(Chat.deleted_at.isnot(None), Chat.deleted_at < before))
        return [row[0] for row in result.all()]
