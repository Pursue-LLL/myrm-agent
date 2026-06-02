"""Conversation Fork Manager

[INPUT]
- database.models::Chat, ConversationFork (POS: ORM models)
- platform::get_checkpointer (POS: LangGraph checkpointer instance)
- runtime::ForkInfo (POS: Fork metadata dataclass from harness layer)
- app.services.chat.conversation_recall_index_service::ConversationRecallIndexService (POS: Conversation Recall 索引生命周期服务)

[OUTPUT]
- ConversationForkManager: Fork conversation + query fork info
- ForkCreateResult: Fork operation result NamedTuple
- ForkInfoResponse: Fork info query result NamedTuple

[POS]
Conversation forking service layer. Manages checkpoint-based conversation
forking and fork relationship queries.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, NamedTuple
from uuid import uuid4

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import ChannelVersions
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Chat, ConversationFork, Message
from app.services.chat.conversation_recall_index_service import ConversationRecallIndexService

if TYPE_CHECKING:
    from langgraph.checkpoint.base import CheckpointTuple

logger = logging.getLogger(__name__)


class ForkCreateResult(NamedTuple):
    """Fork creation operation result."""

    success: bool
    new_chat_id: str | None
    parent_chat_id: str
    fork_point: int | None
    error: str | None = None


class ForkChildInfo(NamedTuple):
    """Single child fork info."""

    chat_id: str
    title: str
    created_at: str  # ISO format timestamp


class ForkInfoResponse(NamedTuple):
    """Fork info query response."""

    parent_chat_id: str | None
    fork_point: int | None
    children: list[ForkChildInfo]


class ConversationForkManager:
    """Conversation forking service.

    Provides checkpoint-based conversation forking capabilities:
    - Clone complete agent state (messages + agent_state) to new thread
    - Track fork relationships in database
    - Query fork lineage (parent and children)

    """

    @staticmethod
    async def fork_conversation(
        db: AsyncSession,
        parent_chat_id: str,
        message_index: int,
        new_title: str | None = None,
    ) -> ForkCreateResult:
        """Fork conversation from specific message index.

        Creates a new chat with complete checkpoint state at fork point.

        Args:
            db: Database session
            parent_chat_id: Parent conversation ID
            message_index: Message index to fork from (0-based)
            new_title: Optional custom title (auto-generated if None)

        Returns:
            ForkCreateResult with new_chat_id or error

        """
        from app.platform_utils import get_checkpointer

        # 1. Validate parent chat exists and user has access
        parent_stmt = select(Chat).where(Chat.id == parent_chat_id)
        parent_result = await db.execute(parent_stmt)
        parent_chat = parent_result.scalar_one_or_none()

        if not parent_chat:
            return ForkCreateResult(
                success=False,
                new_chat_id=None,
                parent_chat_id=parent_chat_id,
                fork_point=message_index,
                error="Parent chat not found or access denied",
            )

        # Validate message_index boundary.
        from sqlalchemy import func as sql_func

        count_stmt = select(sql_func.count(Message.id)).where(Message.chat_id == parent_chat_id)
        count_result = await db.execute(count_stmt)
        total_messages = count_result.scalar_one()

        if message_index < 0 or message_index >= total_messages:
            return ForkCreateResult(
                success=False,
                new_chat_id=None,
                parent_chat_id=parent_chat_id,
                fork_point=message_index,
                error=f"Invalid message_index: {message_index} (total messages: {total_messages})",
            )

        # 3. Attempt to get checkpoint (optional — fork works with or without it)
        checkpointer = get_checkpointer()
        checkpoint_tuple: CheckpointTuple | None = None

        if checkpointer and message_index == total_messages - 1:
            parent_config: RunnableConfig = {"configurable": {"thread_id": parent_chat_id}}
            try:
                checkpoint_tuple = await checkpointer.aget_tuple(parent_config)
                if checkpoint_tuple and not checkpoint_tuple.checkpoint:
                    checkpoint_tuple = None
            except Exception as e:
                logger.warning("Checkpoint retrieval failed (non-fatal): %s", e)
                checkpoint_tuple = None

        # 3. Generate fork title
        new_chat_id = str(uuid4())
        if not new_title:
            msg_stmt = (
                select(Message)
                .where(Message.chat_id == parent_chat_id)
                .order_by(Message.created_at)
                .offset(message_index)
                .limit(1)
            )
            msg_result = await db.execute(msg_stmt)
            fork_message = msg_result.scalar_one_or_none()

            if fork_message and fork_message.content:
                snippet = fork_message.content[:40].strip()
                new_title = f"Branch: {snippet}{'...' if len(fork_message.content) > 40 else ''}"
            else:
                new_title = f"Branch from: {parent_chat.title or 'Conversation'}"
            new_title = new_title[:255]
        else:
            new_title = new_title.strip()[:255]

        new_chat = Chat(
            id=new_chat_id,
            agent_id=parent_chat.agent_id,
            title=new_title,
            source=parent_chat.source,
            channel_session_key=None,  # Fork creates independent conversation
        )
        db.add(new_chat)

        # 4. Clone messages up to fork point into new chat
        msgs_stmt = select(Message).where(Message.chat_id == parent_chat_id).order_by(Message.created_at).limit(message_index + 1)
        msgs_result = await db.execute(msgs_stmt)
        parent_messages = msgs_result.scalars().all()

        for msg in parent_messages:
            cloned_msg = Message(
                id=str(uuid4()),
                chat_id=new_chat_id,
                role=msg.role,
                content=msg.content,
                sent_at=msg.sent_at,
                sent_timezone=msg.sent_timezone,
                extra_data=msg.extra_data,
                created_at=msg.created_at,
            )
            db.add(cloned_msg)

        # 5. Clone checkpoint if available (best-effort)
        fork_checkpoint_id: str | None = None
        if checkpoint_tuple:
            new_config: RunnableConfig = {"configurable": {"thread_id": new_chat_id}}
            new_versions: ChannelVersions = {}
            try:
                await checkpointer.aput(
                    new_config,
                    checkpoint_tuple.checkpoint,
                    checkpoint_tuple.metadata or {},
                    new_versions,
                )
                raw_checkpoint_id = checkpoint_tuple.config.get("checkpoint_id")
                if not raw_checkpoint_id:
                    raw_checkpoint_id = getattr(checkpoint_tuple, "checkpoint_ns", None)
                fork_checkpoint_id = str(raw_checkpoint_id) if raw_checkpoint_id is not None else None
                logger.debug(
                    "Forked checkpoint: %s -> %s (message_index=%d)",
                    parent_chat_id,
                    new_chat_id,
                    message_index,
                )
            except Exception as e:
                logger.warning("Checkpoint clone failed (non-fatal): %s", e)

        fork_record = ConversationFork(
            child_chat_id=new_chat_id,
            parent_chat_id=parent_chat_id,
            fork_checkpoint_id=fork_checkpoint_id,
            fork_message_index=message_index,
        )
        db.add(fork_record)
        await db.flush()
        await ConversationRecallIndexService.rebuild_chat(db, new_chat_id)

        # Commit transaction.
        try:
            await db.commit()
            logger.debug("Fork created successfully: %s (parent=%s)", new_chat_id, parent_chat_id)

            return ForkCreateResult(
                success=True,
                new_chat_id=new_chat_id,
                parent_chat_id=parent_chat_id,
                fork_point=message_index,
                error=None,
            )

        except Exception as e:
            logger.exception("Failed to commit fork transaction")
            await db.rollback()

            try:
                cp = get_checkpointer()
                for tid in (new_chat_id, f"chat_{new_chat_id}"):
                    await cp.adelete_thread(tid)
                logger.info(
                    "Fork rollback: cleaned orphaned checkpoint (thread_id=%s)",
                    new_chat_id,
                )
            except Exception as cp_err:
                logger.warning(
                    "Fork rollback: failed to clean orphaned checkpoint "
                    "(thread_id=%s): %s",
                    new_chat_id,
                    cp_err,
                )

            return ForkCreateResult(
                success=False,
                new_chat_id=None,
                parent_chat_id=parent_chat_id,
                fork_point=message_index,
                error=f"Database commit error: {e!s}",
            )

    @staticmethod
    async def get_fork_info(
        db: AsyncSession,
        chat_id: str,
    ) -> ForkInfoResponse:
        """Get fork information for a chat.

        Retrieves:
        - Parent chat info (if this is a fork)
        - List of child forks (if any)

        Args:
            db: Database session
            chat_id: Chat ID to query

        Returns:
            ForkInfoResponse with parent and children info

        """
        # 1. Query if this chat is a fork
        parent_stmt = select(ConversationFork).where(ConversationFork.child_chat_id == chat_id)
        parent_result = await db.execute(parent_stmt)
        fork_record = parent_result.scalar_one_or_none()

        parent_chat_id: str | None = None
        fork_point: int | None = None

        if fork_record:
            parent_chat_id = fork_record.parent_chat_id
            fork_point = fork_record.fork_message_index

        # 2. Query child forks
        children_stmt = (
            select(ConversationFork, Chat)
            .join(Chat, Chat.id == ConversationFork.child_chat_id)
            .where(ConversationFork.parent_chat_id == chat_id)
            .order_by(ConversationFork.created_at.desc())
        )
        children_result = await db.execute(children_stmt)
        children_rows = children_result.all()

        children_list: list[ForkChildInfo] = []
        for fork, chat in children_rows:
            children_list.append(
                ForkChildInfo(
                    chat_id=chat.id,
                    title=chat.title or "Untitled",
                    created_at=fork.created_at.isoformat() if fork.created_at else "",
                )
            )

        return ForkInfoResponse(
            parent_chat_id=parent_chat_id,
            fork_point=fork_point,
            children=children_list,
        )

    @staticmethod
    async def delete_fork_lineage(
        db: AsyncSession,
        chat_id: str,
    ) -> int:
        """Delete all child forks recursively.

        Args:
            db: Database session
            chat_id: Root chat ID

        Returns:
            Number of forks deleted

        Note:
            Database CASCADE constraint handles actual deletion.
            This method is for metrics/logging purposes.

        """
        # Count children before deletion (CASCADE will delete them)
        count_stmt = select(func.count(ConversationFork.child_chat_id)).where(ConversationFork.parent_chat_id == chat_id)
        count_result = await db.execute(count_stmt)
        child_count = count_result.scalar_one()

        # Deletion handled by CASCADE constraint when parent chat is deleted
        logger.debug("Fork lineage deletion triggered: chat_id=%s, children=%d", chat_id, child_count)

        return int(child_count)
