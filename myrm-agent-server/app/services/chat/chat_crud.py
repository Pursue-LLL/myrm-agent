"""Chat CRUD, session management, and channel operations mixin.

[INPUT]
- _base::_ChatServiceBase, _ChatRepositoryPort (POS: repository 协议和访问器)
- database.dto::ChatCreate, ChatDTO, MessageCreate, MessageDTO (POS: 数据传输对象)
- conversation_recall_index_service::ConversationRecallIndexService (POS: Conversation Recall 索引生命周期服务)

[OUTPUT]
- _ChatCrudMixin: Chat CRUD、session flush、channel chat 管理方法

[POS]
Chat CRUD 编排层。提供聊天会话的创建、读取、更新、删除，
以及 Focus & Flush 会话刷新和频道聊天管理。
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from app.database.dto import ChatCreate, ChatDTO, MessageCreate, MessageDTO
from app.database.repositories.uow import UnitOfWork
from app.services.external_agents.runtime_pool_registry import close_external_agent_pool_for_chat

from ._base import _ChatServiceBase

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
from .conversation_recall_index_service import ConversationRecallIndexService

logger = logging.getLogger(__name__)


class _ChatCrudMixin(_ChatServiceBase):
    """Chat CRUD, session, and channel operations."""

    @staticmethod
    async def get_chat_list(
        page: int = 1,
        page_size: int = 10,
        source: str | None = None,
        project_id: str | None = None,
        unassigned: bool = False,
        keyword: str | None = None,
    ) -> tuple[list[ChatDTO], int]:
        """获取聊天列表（支持分页、来源、项目和关键词过滤）"""
        offset = (page - 1) * page_size
        async with UnitOfWork() as uow:
            return await _ChatServiceBase._cr(uow).get_chats_paginated(
                offset,
                page_size,
                source=source,
                project_id=project_id,
                unassigned=unassigned,
                keyword=keyword,
            )

    @staticmethod
    async def get_chat_by_id(chat_id: str) -> ChatDTO | None:
        """根据ID获取聊天详情（含 messages relationship）"""
        async with UnitOfWork() as uow:
            return await _ChatServiceBase._cr(uow).get_chat_by_id(chat_id, load_messages=True)

    @staticmethod
    async def get_chat_metadata(chat_id: str) -> ChatDTO | None:
        """根据 ID 获取 Chat 元数据（不加载 messages，用于权限检查等轻量场景）"""
        async with UnitOfWork() as uow:
            return await _ChatServiceBase._cr(uow).get_chat_by_id(chat_id, load_messages=False)

    @staticmethod
    async def ensure_default_workspace_dir(chat_id: str) -> str | None:
        """Bind ``chat_{chat_id}`` sandbox path when ``workspace_dir`` is unset.

        Used by GET chat metadata so the frontend can open Active Working Memory
        previews even if the agent round-trip did not persist ``workspace_dir`` yet.
        """
        try:
            from pathlib import Path

            from myrm_agent_harness.toolkits.code_execution import (
                create_workspace_service,
            )

            from app.config.settings import get_settings

            session_id = f"chat_{chat_id}"
            workspace_svc = create_workspace_service(
                root_dir=Path(get_settings().database.harness_dir),
            )
            workspace = await workspace_svc.get_or_create(session_id=session_id)
            resolved = workspace_svc.get_workspace_absolute_path(workspace)
            await _ChatCrudMixin.update_chat_fields(chat_id, {"workspace_dir": resolved})
            return resolved
        except Exception as exc:
            logger.warning(
                "Failed to JIT-bind default workspace for chat %s: %s",
                chat_id,
                exc,
            )
            return None

    @staticmethod
    async def count_messages(chat_id: str) -> int:
        """获取聊天消息总数（SQL COUNT，不加载到内存）"""
        async with UnitOfWork() as uow:
            return await _ChatServiceBase._cr(uow).count_messages(chat_id)

    @staticmethod
    async def create_or_update_chat(chat_data: ChatCreate) -> ChatDTO:
        """创建或更新聊天会话"""
        async with UnitOfWork() as uow:
            existing_chat = await _ChatServiceBase._cr(uow).get_chat_by_id(chat_data.chat_id, load_messages=False)
            title = chat_data.title
            first_message = None
            if chat_data.messages:
                first_user_msg = next((msg for msg in chat_data.messages if msg.role == "user"), None)
                if first_user_msg:
                    first_message = first_user_msg.content
                    if not title:
                        title = first_user_msg.content[:50]
            if existing_chat:
                updates: dict[str, object] = {
                    "title": title or existing_chat.title,
                    "action_mode": chat_data.action_mode,
                    "agent_id": chat_data.agent_id,
                    "last_message": chat_data.last_message or existing_chat.last_message,
                }
                if chat_data.ephemeral_subagents is not None:
                    updates["ephemeral_subagents"] = chat_data.ephemeral_subagents
                if chat_data.task_adaptive_digest is not None:
                    updates["task_adaptive_digest"] = chat_data.task_adaptive_digest
                if chat_data.is_incognito is not None:
                    updates["is_incognito"] = chat_data.is_incognito
                if first_message or not existing_chat.first_message:
                    updates["first_message"] = first_message
                await _ChatServiceBase._cr(uow).update_chat_fields(existing_chat.id, updates)
                chat = existing_chat
                for k, v in updates.items():
                    setattr(chat, k, v)
                chat.updated_at = datetime.utcnow()
            else:
                chat = ChatDTO(
                    id=chat_data.chat_id,
                    title=title,
                    action_mode=chat_data.action_mode,
                    agent_id=chat_data.agent_id,
                    last_message=chat_data.last_message,
                    first_message=first_message,
                    ephemeral_subagents=chat_data.ephemeral_subagents,
                    task_adaptive_digest=chat_data.task_adaptive_digest,
                    is_incognito=chat_data.is_incognito,
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow(),
                )
                await _ChatServiceBase._cr(uow).add_chat(chat)

            await _ChatCrudMixin._update_chat_messages(uow, chat_data.chat_id, chat_data.messages)
            sess = uow.session
            assert sess is not None
            await sess.flush()
            await ConversationRecallIndexService.rebuild_chat(sess, chat_data.chat_id)
            return chat

    @staticmethod
    async def _update_chat_messages(uow: UnitOfWork, chat_id: str, messages: list[MessageCreate]) -> None:
        """更新聊天消息（内部方法）"""
        message_ids = [msg.messageId for msg in messages]
        if len(message_ids) != len(set(message_ids)):
            from collections import Counter

            id_counts = Counter(message_ids)
            duplicates = [msg_id for msg_id, count in id_counts.items() if count > 1]
            raise ValueError(f"在同一个聊天会话中发现重复的messageId: {', '.join(duplicates)}")
        new_messages = [
            MessageDTO(
                id=msg.messageId,
                chat_id=chat_id,
                role=msg.role,
                content=msg.content,
                extra_data=msg.metadata,
                created_at=msg.createdAt or datetime.utcnow(),
                sent_at=msg.createdAt or datetime.utcnow(),
                sent_timezone="UTC",
            )
            for msg in messages
        ]
        await _ChatServiceBase._cr(uow).delete_all_messages_for_chat(chat_id)
        await _ChatServiceBase._cr(uow).add_messages(new_messages)
        if messages:
            from myrm_agent_harness.utils.text_sanitizer import (
                extract_and_strip_think_blocks,
            )

            clean_content, _ = extract_and_strip_think_blocks(messages[-1].content)
            new_last = clean_content[:100]
        else:
            new_last = ""
        if new_last:
            await _ChatServiceBase._cr(uow).update_chat_fields(chat_id, {"last_message": new_last})

    @staticmethod
    async def update_chat_title(chat_id: str, title: str) -> ChatDTO | None:
        """更新聊天标题"""
        async with UnitOfWork() as uow:
            chat = await _ChatServiceBase._cr(uow).get_chat_by_id(chat_id)
            if not chat:
                return None
            await _ChatServiceBase._cr(uow).update_chat_fields(chat_id, {"title": title})
            sess = uow.session
            assert sess is not None
            await sess.flush()
            await ConversationRecallIndexService.rebuild_chat(sess, chat_id)
            chat.title = title
            return chat

    @staticmethod
    async def update_chat_fields(chat_id: str, updates: dict[str, object]) -> None:
        """Update arbitrary fields on a chat record."""
        async with UnitOfWork() as uow:
            await _ChatServiceBase._cr(uow).update_chat_fields(chat_id, updates)

    @staticmethod
    async def update_message_extra_data(message_id: str, extra_data: dict[str, object]) -> None:
        """Update extra_data for a message record."""
        async with UnitOfWork() as uow:
            await _ChatServiceBase._cr(uow).update_message_extra_data(message_id, extra_data)

    @staticmethod
    async def delete_chat(chat_id: str) -> bool:
        """Soft-delete a chat session (moves to trash)."""
        async with UnitOfWork() as uow:
            repo = _ChatServiceBase._cr(uow)
            ok = await repo.soft_delete_chat(chat_id)
            if not ok:
                return False
        await ConversationRecallIndexService.set_chat_excluded(chat_id, excluded=True)
        await close_external_agent_pool_for_chat(chat_id)
        return True

    @staticmethod
    async def batch_delete(chat_ids: list[str]) -> dict[str, int]:
        """Batch soft-delete multiple chat sessions (move to trash).

        Returns a dict with 'deleted' and 'failed' counts.
        """
        deleted = 0
        failed = 0
        for chat_id in chat_ids:
            ok = await _ChatCrudMixin.delete_chat(chat_id)
            if ok:
                deleted += 1
            else:
                failed += 1
        return {"deleted": deleted, "failed": failed}

    @staticmethod
    async def permanently_delete_chat(chat_id: str) -> bool:
        """Permanently delete a trashed chat and its workspace, including derived memories."""
        sandbox_base_dir: str | None = None
        async with UnitOfWork() as uow:
            repo = _ChatServiceBase._cr(uow)
            sess = uow.session
            assert sess is not None
            chat = await repo.get_chat_by_id(chat_id, load_messages=False)
            if chat:
                sandbox_base_dir = chat.sandbox_base_dir
            await ConversationRecallIndexService.delete_chat(sess, chat_id)
            await _delete_widget_kv_for_chat(sess, chat_id)
            ok = await repo.permanently_delete_chat(chat_id)

        if ok:
            await _cascade_delete_memories(chat_id)
            await _ChatCrudMixin._cleanup_checkpointer(chat_id)
            if sandbox_base_dir:
                try:
                    from app.services.chat.sandbox_worktree import cleanup_sandbox_worktree

                    await cleanup_sandbox_worktree(sandbox_base_dir, chat_id)
                except Exception as e:
                    logger.warning("Sandbox worktree cleanup failed (chat=%s): %s", chat_id, e)
            try:
                from app.services.infra.sandbox_cleanup import cleanup_chat_workspace

                results = await cleanup_chat_workspace(chat_id)
                logger.info("Chat workspace cleaned (chat=%s): %s", chat_id, results)
            except Exception as e:
                logger.error("Chat workspace cleanup failed (chat=%s): %s", chat_id, e)
            await close_external_agent_pool_for_chat(chat_id)
        return ok

    @staticmethod
    async def restore_chat(chat_id: str) -> bool:
        """Restore a trashed chat back to active."""
        async with UnitOfWork() as uow:
            repo = _ChatServiceBase._cr(uow)
            ok = await repo.restore_chat(chat_id)
            if not ok:
                return False
        await ConversationRecallIndexService.set_chat_excluded(chat_id, excluded=False)
        return True

    @staticmethod
    async def get_trashed_chats(page: int = 1, page_size: int = 20) -> tuple[list[ChatDTO], int]:
        """List trashed chats with pagination."""
        offset = (page - 1) * page_size
        async with UnitOfWork() as uow:
            return await _ChatServiceBase._cr(uow).get_trashed_chats_paginated(offset, page_size)

    @staticmethod
    async def count_trashed_chats() -> int:
        """Return count of trashed chats (for badge display)."""
        async with UnitOfWork() as uow:
            return await _ChatServiceBase._cr(uow).count_trashed()

    @staticmethod
    async def empty_trash() -> int:
        """Permanently delete all trashed chats and clean workspaces, including derived memories."""
        async with UnitOfWork() as uow:
            repo = _ChatServiceBase._cr(uow)
            trashed, _ = await repo.get_trashed_chats_paginated(0, 10000)
            chat_ids = [c.id for c in trashed]
            sandbox_map = {c.id: c.sandbox_base_dir for c in trashed if c.sandbox_base_dir}
            sess = uow.session
            assert sess is not None
            for cid in chat_ids:
                await ConversationRecallIndexService.delete_chat(sess, cid)
            count = await repo.empty_trash()

        for cid in chat_ids:
            await _cascade_delete_memories(cid)
            await _ChatCrudMixin._cleanup_checkpointer(cid)
            if cid in sandbox_map:
                try:
                    from app.services.chat.sandbox_worktree import cleanup_sandbox_worktree

                    await cleanup_sandbox_worktree(sandbox_map[cid], cid)
                except Exception as e:
                    logger.warning("Sandbox worktree cleanup failed during empty_trash (chat=%s): %s", cid, e)
            try:
                from app.services.infra.sandbox_cleanup import cleanup_chat_workspace

                await cleanup_chat_workspace(cid)
            except Exception as e:
                logger.error("Workspace cleanup failed during empty_trash (chat=%s): %s", cid, e)
            await close_external_agent_pool_for_chat(cid)
        return count

    @staticmethod
    async def _cleanup_checkpointer(chat_id: str) -> None:
        """Clear LangGraph checkpointer state for a chat session.

        Uses the standard ``adelete_thread`` API provided by all LangGraph
        checkpointer backends (MemorySaver, AsyncSqliteSaver).
        Idempotent: deleting a non-existent thread is a no-op.
        """
        try:
            from app.platform_utils import get_checkpointer

            cp = get_checkpointer()
            for tid in (chat_id, f"chat_{chat_id}"):
                await cp.adelete_thread(tid)
            logger.info("Cleared LangGraph checkpointer (chat=%s)", chat_id)
        except Exception as e:
            logger.warning(
                "Failed to clear LangGraph checkpointer (chat=%s): %s",
                chat_id,
                e,
            )

    @staticmethod
    async def focus_flush_session(chat_id: str) -> bool:
        """Soft-delete all messages to flush LLM context while retaining sandbox."""
        async with UnitOfWork() as uow:
            chat = await _ChatServiceBase._cr(uow).get_chat_by_id(chat_id, load_messages=False)
            if not chat:
                return False

            await _ChatServiceBase._cr(uow).soft_delete_all_messages_for_chat(chat_id)

            updates: dict[str, object] = {
                "last_message": None,
                "first_message": None,
                "compacted_summary": None,
                "compacted_before_id": None,
                "compacted_at": None,
            }
            await _ChatServiceBase._cr(uow).update_chat_fields(chat_id, updates)

            sess = uow.session
            assert sess is not None
            await ConversationRecallIndexService.delete_chat(sess, chat_id)

        await _ChatCrudMixin._cleanup_checkpointer(chat_id)
        return True

    @staticmethod
    async def get_channel_chat_by_key(user_id_or_session_key: str, session_key: str | None = None) -> ChatDTO | None:
        """Resolve channel chat; supports ``get_channel_chat_by_key(session_key)`` or
        ``get_channel_chat_by_key(user_id, session_key)`` (user_id is ignored for lookup).
        """
        key = session_key if session_key is not None else user_id_or_session_key
        async with UnitOfWork() as uow:
            return await _ChatServiceBase._cr(uow).get_channel_chat_by_key(key)

    @staticmethod
    async def get_or_create_channel_chat(
        first: str,
        second: str,
        source: str | None = None,
        *,
        agent_id: str | None = None,
    ) -> ChatDTO:
        """``get_or_create_channel_chat(session_key, source)`` or
        ``get_or_create_channel_chat(user_id, session_key, source)``.
        """
        if source is None:
            channel_session_key, src = first, second
        else:
            _, channel_session_key, src = first, second, source
        async with UnitOfWork() as uow:
            chat = await _ChatServiceBase._cr(uow).get_channel_chat_by_key(channel_session_key)
            if chat:
                if agent_id and chat.agent_id != agent_id:
                    await _ChatServiceBase._cr(uow).update_chat_fields(chat.id, {"agent_id": agent_id})
                    return chat.model_copy(update={"agent_id": agent_id})
                return chat
            from sqlalchemy.exc import IntegrityError

            new_chat = ChatDTO(
                id=str(uuid4()),
                agent_id=agent_id,
                source=src,
                channel_session_key=channel_session_key,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            await _ChatServiceBase._cr(uow).add_chat(new_chat)
            try:
                sess = uow.session
                assert sess is not None
                await sess.flush()
            except IntegrityError:
                sess = uow.session
                assert sess is not None
                await sess.rollback()
                chat = await _ChatServiceBase._cr(uow).get_channel_chat_by_key(channel_session_key)
                if chat:
                    return chat
                raise
            return new_chat

    # ── Pinned Threads ──────────────────────────────────────────────

    MAX_PINNED = 9

    @staticmethod
    async def pin_chat(chat_id: str) -> ChatDTO:
        async with UnitOfWork() as uow:
            repo = _ChatServiceBase._cr(uow)
            chat = await repo.get_chat_by_id(chat_id, load_messages=False)
            if not chat:
                raise LookupError(f"Chat {chat_id} not found")
            if chat.is_pinned:
                return chat
            count = await repo.count_pinned()
            if count >= _ChatCrudMixin.MAX_PINNED:
                raise ValueError(f"Cannot pin more than {_ChatCrudMixin.MAX_PINNED} chats")
            next_order = await repo.get_next_pin_order()
            await repo.pin_chat(chat_id, next_order)
            chat.is_pinned = True
            chat.pin_order = next_order
            return chat

    @staticmethod
    async def unpin_chat(chat_id: str) -> None:
        async with UnitOfWork() as uow:
            repo = _ChatServiceBase._cr(uow)
            chat = await repo.get_chat_by_id(chat_id, load_messages=False)
            if not chat:
                raise LookupError(f"Chat {chat_id} not found")
            await repo.unpin_chat(chat_id)

    @staticmethod
    async def reorder_pinned_chats(items: list[tuple[str, int]]) -> None:
        if len(items) > _ChatCrudMixin.MAX_PINNED:
            raise ValueError(f"Cannot reorder more than {_ChatCrudMixin.MAX_PINNED} items")
        async with UnitOfWork() as uow:
            await _ChatServiceBase._cr(uow).reorder_pinned_chats(items)

    @staticmethod
    async def get_cascade_info(chat_id: str) -> dict[str, int]:
        """Count memories linked to a chat session (for deletion preview)."""
        try:
            from app.core.memory import get_cascade_memory_manager

            manager = await get_cascade_memory_manager()
            return await manager.count_by_source_chat_id(chat_id)
        except Exception as e:
            logger.warning("Failed to get cascade info (chat=%s): %s", chat_id, e)
            return {}


async def _delete_widget_kv_for_chat(session: AsyncSession, chat_id: str) -> None:
    """Remove all widget KV entries associated with a chat."""
    from sqlalchemy import delete

    from app.database.models.widget_kv import WidgetKVEntry

    stmt = delete(WidgetKVEntry).where(WidgetKVEntry.chat_id == chat_id)
    await session.execute(stmt)


async def _cascade_delete_memories(chat_id: str) -> None:
    """Cascade-delete all memories derived from a chat session (Right to be Forgotten)."""
    try:
        from app.core.memory import get_cascade_memory_manager

        manager = await get_cascade_memory_manager()
        counts = await manager.purge_by_source_chat_id(chat_id)
        if any(counts.values()):
            logger.info("Cascade deleted memories for chat=%s: %s", chat_id, counts)
    except Exception as e:
        logger.warning("Cascade memory deletion failed (chat=%s): %s", chat_id, e)
