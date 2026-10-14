"""Chat CRUD, session flush and pinned-thread operations mixin.

[INPUT]
- _base::_ChatServiceBase, _ChatRepositoryPort (POS: repository 协议和访问器)
- database.dto::ChatCreate, ChatDTO, MessageCreate, MessageDTO (POS: 数据传输对象)
- chat_disposal (POS: 会话结束后的统一拆除步骤)
- conversation_recall_index_service::ConversationRecallIndexService (POS: Conversation Recall 索引生命周期服务)

[OUTPUT]
- _ChatCrudMixin: Chat CRUD、session flush、Pinned Threads、`ensure_chat_source`（cron 打标并同步 recall 索引 source）

[POS]
Chat CRUD 编排层。提供聊天会话的创建、读取、更新，以及 Focus & Flush 会话刷新和置顶管理；
删除生命周期在 ``chat_deletion``，渠道聊天在 ``chat_channel``。
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING

from app.database.dto import ChatCreate, ChatDTO, MessageCreate, MessageDTO
from app.database.repositories.uow import UnitOfWork

from . import chat_disposal
from ._base import _ChatServiceBase
from .conversation_recall_index_service import ConversationRecallIndexService

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class _ChatCrudMixin(_ChatServiceBase):
    """Chat CRUD, session flush and pinned-thread operations."""

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
