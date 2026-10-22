"""Chat history sync repository.

[INPUT]
app.database.models::Chat, Message (POS: 会话与消息域模型。管理聊天会话、消息记录和对话分支)
sqlalchemy.ext.asyncio::AsyncSession (POS: async database session)

[OUTPUT]
ConversationBranch: the stored conversation a chat's agent thread has to mirror.
ChatHistorySyncRepository: load the branch, check that a turn's answer is stored, read and write the sync token.

[POS]
聊天历史同步仓储。读取「当前活跃分支 + 压缩摘要」的快照，并读写 Chat.history_sync_token；
分支范围与 `load_web_chat_history` 一致（压缩锚点之后的活跃消息），但不受历史条数上限约束。
"""

from __future__ import annotations

from typing import NamedTuple

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Chat, Message


class ConversationBranch(NamedTuple):
    """The stored conversation of a chat: compaction state plus the ordered ids of its active messages."""

    stored_token: str | None
    compacted_summary: str | None
    compacted_before_id: str | None
    message_ids: tuple[str, ...]


class ChatHistorySyncRepository:
    """Reads and writes what the agent's checkpoint thread of a chat has to be compared with."""

    @staticmethod
    async def load_branch(
        db: AsyncSession,
        chat_id: str,
        *,
        exclude_message_id: str | None = None,
    ) -> ConversationBranch | None:
        """Return the active branch after the compaction anchor, or ``None`` when the chat does not exist.

        Messages are ordered by ``(created_at, id)`` so equal timestamps still give one stable order.
        """
        chat_row = (
            await db.execute(
                select(Chat.history_sync_token, Chat.compacted_summary, Chat.compacted_before_id).where(Chat.id == chat_id)
            )
        ).one_or_none()
        if chat_row is None:
            return None
        stored_token, summary, before_id = chat_row

        query = select(Message.id).where(Message.chat_id == chat_id, Message.is_active)
        if exclude_message_id:
            query = query.where(Message.id != exclude_message_id)
        if summary and before_id:
            anchor_created_at = select(Message.created_at).where(Message.id == before_id).scalar_subquery()
            query = query.where(Message.created_at > anchor_created_at)
        ids = (await db.execute(query.order_by(Message.created_at, Message.id))).scalars().all()
        return ConversationBranch(
            stored_token=stored_token,
            compacted_summary=summary,
            compacted_before_id=before_id,
            message_ids=tuple(ids),
        )

    @staticmethod
    async def has_active_answer(db: AsyncSession, chat_id: str, request_message_id: str) -> bool:
        """Whether the assistant row written for the request ``request_message_id`` is stored and active."""
        row = await db.execute(
            select(Message.id)
            .where(
                Message.chat_id == chat_id,
                Message.role == "assistant",
                Message.is_active,
                func.json_extract(Message.extra_data, "$.request_message_id") == request_message_id,
            )
            .limit(1)
        )
        return row.first() is not None

    @staticmethod
    async def store_token(db: AsyncSession, chat_id: str, token: str | None) -> None:
        """Write the token without touching ``updated_at``: bookkeeping is not chat activity."""
        await db.execute(update(Chat).where(Chat.id == chat_id).values(history_sync_token=token, updated_at=Chat.updated_at))
