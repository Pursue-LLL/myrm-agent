"""Chat CRUD, session management, and channel operations mixin.

[INPUT]
- _base::_ChatServiceBase, _ChatRepositoryPort (POS: repository 协议和访问器)
- database.dto::ChatCreate, ChatDTO, MessageCreate, MessageDTO (POS: 数据传输对象)
- conversation_recall_index_service::ConversationRecallIndexService (POS: Conversation Recall 索引生命周期服务)
- services.memory.consolidation_service::ConsolidationService (POS: 记忆工作台与巩固服务)

[OUTPUT]
- _ChatCrudMixin: Chat CRUD、session flush、channel chat 管理、`ensure_chat_source`（cron 打标并同步 recall 索引 source）

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

from . import chat_disposal
from ._base import _ChatServiceBase
from .chat_bound_rows import delete_trashed_chat_bound_rows

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
        tags: list[str] | None = None,
        match_mode: str = "any",
    ) -> tuple[list[ChatDTO], int]:
        """获取聊天列表（支持分页、来源、项目、关键词及多维度标签过滤）"""
        offset = (page - 1) * page_size
        async with UnitOfWork() as uow:
            return await _ChatServiceBase._cr(uow).get_chats_paginated(
                offset,
                page_size,
                source=source,
                project_id=project_id,
                unassigned=unassigned,
                keyword=keyword,
                tags=tags,
                match_mode=match_mode,
            )

    @staticmethod
    async def update_chat_tags(chat_id: str, tags: list[str]) -> list[str]:
        """更新会话关联的多维度层级标签列表"""
        async with UnitOfWork() as uow:
            updated_tags = await _ChatServiceBase._cr(uow).update_chat_tags(chat_id, tags)
            await uow.commit()
            return updated_tags

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
    async def ensure_chat_source(chat_id: str, source: str) -> None:
        """Tag cron-owned chats for recall ranking without overwriting channel sources."""
        normalized = source.strip().lower()
        if normalized != "cron":
            return
        async with UnitOfWork() as uow:
            session = uow.session
            if session is None:
                return
            from sqlalchemy import text

            await session.execute(
                text(
                    """
                    UPDATE chats
                    SET source = :source, updated_at = CURRENT_TIMESTAMP
                    WHERE id = :chat_id
                      AND source = 'web'
                """
                ),
                {"chat_id": chat_id, "source": normalized},
            )
            await session.execute(
                text(
                    """
                    UPDATE conversation_recall_documents
                    SET source = (SELECT source FROM chats WHERE id = :chat_id),
                        updated_at = CURRENT_TIMESTAMP
                    WHERE chat_id = :chat_id
                """
                ),
                {"chat_id": chat_id},
            )

    @staticmethod
    async def ensure_default_workspace_dir(chat_id: str) -> str | None:
        """Resolve SSOT workspace for a chat (project bind > chat dir > JIT sandbox).

        Persists JIT sandbox path when created so legacy callers stay in sync with GET chat.
        """
        from app.services.chat.effective_workspace import (
            resolve_effective_chat_workspace,
        )

        chat = await _ChatCrudMixin.get_chat_metadata(chat_id)
        if chat is None:
            return None
        try:
            return await resolve_effective_chat_workspace(
                chat,
                jit_fallback=True,
                persist_jit=True,
            )
        except Exception as exc:
            logger.warning(
                "Failed to resolve default workspace for chat %s: %s",
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
                if chat_data.agent_id and chat_data.agent_id != existing_chat.agent_id:
                    updates["session_loaded_skill_names"] = None
                if chat_data.ephemeral_subagents is not None:
                    updates["ephemeral_subagents"] = chat_data.ephemeral_subagents
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
                    is_incognito=chat_data.is_incognito,
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow(),
                )
                await _ChatServiceBase._cr(uow).add_chat(chat)

            await _ChatCrudMixin._update_chat_messages(uow, chat_data.chat_id, chat_data.messages)
            sess = uow.session
            assert sess is not None
            if chat_data.initial_shared_context_ids:
                await _ChatCrudMixin._bind_initial_shared_contexts(sess, chat_data.chat_id, chat_data.initial_shared_context_ids)
            await sess.flush()
            await ConversationRecallIndexService.rebuild_chat(sess, chat_data.chat_id)
            return chat

    @staticmethod
    async def _bind_initial_shared_contexts(sess: AsyncSession, chat_id: str, context_ids: list[str]) -> None:
        """Bind initial shared memory contexts to the conversation within the same transaction."""
        from nanoid import generate as nanoid
        from sqlalchemy import select

        from app.database.models import SharedContextBindingModel, SharedContextModel

        if not context_ids:
            return

        valid_stmt = select(SharedContextModel.id).where(
            SharedContextModel.id.in_(context_ids),
            SharedContextModel.status == "active",
        )
        valid_res = await sess.execute(valid_stmt)
        valid_ids: set[str] = set(valid_res.scalars().all())

        for cid in context_ids:
            if cid in valid_ids:
                existing_stmt = select(SharedContextBindingModel.id).where(
                    SharedContextBindingModel.context_id == cid,
                    SharedContextBindingModel.target_type == "conversation",
                    SharedContextBindingModel.target_id == chat_id,
                )
                existing = (await sess.execute(existing_stmt)).scalar_one_or_none()
                if existing is None:
                    sess.add(
                        SharedContextBindingModel(
                            id=nanoid(size=16),
                            context_id=cid,
                            target_type="conversation",
                            target_id=chat_id,
                        )
                    )

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
        await chat_disposal.clear_runtime_caches(chat_id)
        await chat_disposal.clear_extract_retry_queue(chat_id)
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
    async def _read_sandbox_base_dir(chat_id: str) -> str | None:
        """Read the chat sandbox path in a short read-only transaction.

        Kept separate so the delete transaction stays write-only: with a
        deferred BEGIN, a prior SELECT marks the connection read-seen and
        ``factory._escalate_write_transaction`` skips the BEGIN IMMEDIATE
        upgrade, so concurrent deletes abort with SQLITE_BUSY_SNAPSHOT — a
        lock the busy_timeout PRAGMA cannot resolve.
        """
        async with UnitOfWork() as uow:
            chat = await _ChatServiceBase._cr(uow).get_chat_by_id(chat_id, load_messages=False, include_trashed=True)
            return chat.sandbox_base_dir if chat else None

    @staticmethod
    async def permanently_delete_chat(chat_id: str) -> bool:
        """Permanently delete a trashed chat and its workspace, including derived memories."""
        sandbox_base_dir: str | None = await _ChatCrudMixin._read_sandbox_base_dir(chat_id)
        async with UnitOfWork() as uow:
            repo = _ChatServiceBase._cr(uow)
            sess = uow.session
            assert sess is not None
            # Both deletes act only on a chat that is in the trash, so a stale trash view erases nothing.
            await delete_trashed_chat_bound_rows(sess, [chat_id])
            ok = await repo.permanently_delete_chat(chat_id)
            if ok:
                await ConversationRecallIndexService.delete_chat(sess, chat_id)

        if ok:
            await chat_disposal.dispose_permanently_deleted_chats({chat_id: sandbox_base_dir})
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
            trashed, _ = await _ChatServiceBase._cr(uow).get_trashed_chats_paginated(0, 10000)
            chat_ids = [c.id for c in trashed]
            sandbox_map = {c.id: c.sandbox_base_dir for c in trashed if c.sandbox_base_dir}
        if not chat_ids:
            return 0
        async with UnitOfWork() as uow:
            repo = _ChatServiceBase._cr(uow)
            sess = uow.session
            assert sess is not None
            await delete_trashed_chat_bound_rows(sess, chat_ids)
            for cid in chat_ids:
                await ConversationRecallIndexService.delete_chat(sess, cid)
            count = await repo.empty_trash()

        await chat_disposal.dispose_permanently_deleted_chats({cid: sandbox_map.get(cid) for cid in chat_ids})
        return count

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

        await chat_disposal.clear_conversation_state(chat_id)
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

    @staticmethod
    async def count_orphan_empty_sessions(older_than_minutes: int = 15) -> int:
        """Count legacy orphan sessions lacking assistant messages."""
        from app.core.infra.health.session_diagnostics import (
            count_orphan_empty_sessions,
        )

        return await count_orphan_empty_sessions(older_than_minutes=older_than_minutes)

    @staticmethod
    async def purge_orphan_empty_sessions(older_than_minutes: int = 15) -> int:
        """Purge legacy orphan sessions lacking assistant messages."""
        from app.core.infra.health.session_diagnostics import (
            purge_orphan_empty_sessions,
        )

        return await purge_orphan_empty_sessions(older_than_minutes=older_than_minutes)
