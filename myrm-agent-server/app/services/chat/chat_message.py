"""Message persistence mixin.

[INPUT]
- _base::_ChatServiceBase, _ChatRepositoryPort (POS: repository 协议和访问器)
- database.dto::MessageDTO (POS: 消息数据传输对象)
- chat_helpers::ALLOWED_MESSAGE_ROLES (POS: 合法消息角色集合)
- conversation_recall_index_service::ConversationRecallIndexService (POS: Conversation Recall 索引生命周期服务)
- chat_usage_sync::sync_chat_usage (POS: Chat.total_* 用量缓存重建)
- chat_memory_events::record_memory_influence_event (POS: 记忆影响账本投影)

[OUTPUT]
- _ChatMessageMixin: 消息追加、分页查询、全量查询、按 id 查询、assistant 消息安全持久化

[POS]
消息持久化编排层。提供消息追加（含自动 chat 元数据更新）、
分页查询、全量查询和 assistant 消息安全持久化（含用量同步与 memory_recall trace 投影）。
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from uuid import uuid4

from app.database.dto import ChatDTO, MessageDTO
from app.database.repositories.uow import UnitOfWork

from ._base import _ChatServiceBase
from .chat_helpers import ALLOWED_MESSAGE_ROLES
from .chat_memory_events import record_memory_influence_event
from .chat_usage_sync import sync_chat_usage
from .conversation_recall_index_service import ConversationRecallIndexService

logger = logging.getLogger(__name__)

_RECALL_INDEX_TIMEOUT_SECONDS = 2.0


class _ChatMessageMixin(_ChatServiceBase):
    """Message persistence operations."""

    @staticmethod
    async def _append_recall_index_after_primary_commit(
        uow: UnitOfWork,
        *,
        chat_id: str,
        message_id: str,
        role: str,
        content: str,
        sent_at: datetime,
    ) -> None:
        """Persist the derived recall index without gating the canonical message row.

        Chat/message rows are the source of truth.  The recall tables are rebuilt by
        startup bootstrap when this bounded best-effort side effect is unavailable.
        Keeping the index out of the primary transaction prevents SQLite/FTS locks
        from hiding a user turn from the next request.
        """
        session = uow.session
        assert session is not None
        try:
            await asyncio.wait_for(
                ConversationRecallIndexService.append_message(
                    session,
                    chat_id=chat_id,
                    message_id=message_id,
                    role=role,
                    content=content,
                    sent_at=sent_at,
                ),
                timeout=_RECALL_INDEX_TIMEOUT_SECONDS,
            )
            await uow.commit()
        except TimeoutError:
            await uow.rollback()
            logger.warning(
                "Conversation recall index timed out after %.2fs; canonical message committed chat_id=%s message_id=%s",
                _RECALL_INDEX_TIMEOUT_SECONDS,
                chat_id,
                message_id,
            )
        except Exception:
            await uow.rollback()
            logger.warning(
                "Conversation recall index append failed; canonical message committed chat_id=%s message_id=%s",
                chat_id,
                message_id,
                exc_info=True,
            )

    @staticmethod
    async def append_message(
        chat_id: str,
        role: str,
        content: str,
        sent_at: datetime,
        sent_timezone: str,
        message_id: str | None = None,
        extra_data: dict[str, object] | None = None,
        sibling_group_id: str | None = None,
    ) -> MessageDTO:
        if role not in ALLOWED_MESSAGE_ROLES:
            raise ValueError(f"Invalid message role: {role!r}. Must be one of {ALLOWED_MESSAGE_ROLES}")

        try:
            from app.core.eval.adaptive import mark_chat_activity

            mark_chat_activity()
        except ImportError:
            pass

        async with UnitOfWork() as uow:
            msg = MessageDTO(
                id=message_id or str(uuid4()),
                chat_id=chat_id,
                role=role,
                content=content,
                sent_at=sent_at,
                sent_timezone=sent_timezone,
                extra_data=extra_data,
                sibling_group_id=sibling_group_id,
                created_at=datetime.utcnow(),
            )
            await _ChatServiceBase._cr(uow).add_message(msg)
            msg_updates: dict[str, object] = {"last_message": content[:100]}
            if role == "user":
                chat = await _ChatServiceBase._cr(uow).get_chat_by_id(chat_id)
                if chat and (not chat.first_message):
                    msg_updates["first_message"] = content
                    msg_updates["title"] = content[:50]
            await _ChatServiceBase._cr(uow).update_chat_fields(chat_id, msg_updates)
            sess = uow.session
            assert sess is not None
            await sess.flush()
            await uow.commit()
            await _ChatMessageMixin._append_recall_index_after_primary_commit(
                uow,
                chat_id=chat_id,
                message_id=msg.id,
                role=role,
                content=content,
                sent_at=sent_at,
            )
            return msg

    @staticmethod
    async def ensure_chat_and_append_user_message(
        chat_id: str,
        content: str,
        sent_at: datetime,
        sent_timezone: str,
        message_id: str | None = None,
        action_mode: str = "fast",
        agent_id: str | None = None,
        ephemeral_subagents: dict[str, object] | None = None,
        extra_data: dict[str, object] | None = None,
        is_incognito: bool = False,
        active_moa_preset_id: str | None = None,
        persist_moa_preset: bool = False,
    ) -> MessageDTO:
        try:
            from app.core.eval.adaptive import mark_chat_activity

            mark_chat_activity()
        except ImportError:
            pass

        async with UnitOfWork() as uow:
            chat = await _ChatServiceBase._cr(uow).get_chat_by_id(chat_id)
            if not chat:
                chat = ChatDTO(
                    id=chat_id,
                    agent_id=agent_id,
                    action_mode=action_mode,
                    active_moa_preset_id=(active_moa_preset_id if persist_moa_preset else None),
                    ephemeral_subagents=ephemeral_subagents,
                    is_incognito=is_incognito,
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow(),
                )
                await _ChatServiceBase._cr(uow).add_chat(chat)
                sess = uow.session
                assert sess is not None
                await sess.flush()
            else:
                field_updates: dict[str, object] = {}
                if ephemeral_subagents is not None and chat.ephemeral_subagents != ephemeral_subagents:
                    field_updates["ephemeral_subagents"] = ephemeral_subagents
                if agent_id and chat.agent_id != agent_id:
                    field_updates["agent_id"] = agent_id
                if persist_moa_preset and not is_incognito:
                    field_updates["action_mode"] = action_mode
                    field_updates["active_moa_preset_id"] = active_moa_preset_id
                if field_updates:
                    await _ChatServiceBase._cr(uow).update_chat_fields(chat_id, field_updates)

            resolved_message_id = message_id or str(uuid4())
            if message_id:
                existing = await _ChatServiceBase._cr(uow).get_message_by_id(chat_id, message_id)
                if existing is not None:
                    if existing.role == "user" and existing.content == content:
                        logger.info(
                            "Idempotent user retry detected for message_id=%s chat_id=%s; reusing existing row",
                            message_id,
                            chat_id,
                        )
                        return existing
                    logger.warning(
                        "Duplicate user message_id=%s for chat_id=%s is not idempotent (existing_role=%s); allocating fresh id",
                        message_id,
                        chat_id,
                        existing.role,
                    )
                    resolved_message_id = str(uuid4())

            msg = MessageDTO(
                id=resolved_message_id,
                chat_id=chat_id,
                role="user",
                content=content,
                sent_at=sent_at,
                sent_timezone=sent_timezone,
                extra_data=extra_data,
                created_at=datetime.utcnow(),
            )
            await _ChatServiceBase._cr(uow).add_message(msg)
            last_updates: dict[str, object] = {
                "last_message": content[:100],
                "first_message": content,
                "title": content[:50],
            }
            if chat and chat.first_message:  # already had first message
                last_updates.pop("first_message")
                last_updates.pop("title")
            await _ChatServiceBase._cr(uow).update_chat_fields(chat_id, last_updates)
            sess = uow.session
            assert sess is not None
            await sess.flush()
            await uow.commit()
            await _ChatMessageMixin._append_recall_index_after_primary_commit(
                uow,
                chat_id=chat_id,
                message_id=msg.id,
                role="user",
                content=content,
                sent_at=sent_at,
            )
            return msg

    @staticmethod
    async def get_messages_paginated(
        chat_id: str, *, before: str | None = None, limit: int = 10
    ) -> tuple[list[MessageDTO], bool]:
        limit = min(limit, 100)
        async with UnitOfWork() as uow:
            messages = await _ChatServiceBase._cr(uow).get_messages_paginated(chat_id, before, limit + 1)
            has_more = len(messages) > limit
            result_msgs = list(reversed(messages[:limit]))
            return (result_msgs, has_more)

    @staticmethod
    async def get_all_messages(chat_id: str) -> list[MessageDTO]:
        async with UnitOfWork() as uow:
            return await _ChatServiceBase._cr(uow).get_all_messages(chat_id)

    @staticmethod
    async def get_message_by_id(chat_id: str, message_id: str) -> MessageDTO | None:
        async with UnitOfWork() as uow:
            return await _ChatServiceBase._cr(uow).get_message_by_id(chat_id, message_id)

    @staticmethod
    async def persist_assistant_message_safe(
        chat_id: str,
        content: str,
        extra_data: dict[str, object] | None = None,
        timezone: str | None = None,
        sibling_group_id: str | None = None,
        request_message_id: str | None = None,
    ) -> None:
        if not content.strip() and not extra_data:
            return
        try:
            from datetime import timezone as tz

            if request_message_id:
                extra_data = {
                    **({} if extra_data is None else extra_data),
                    "request_message_id": request_message_id,
                }
            sent_at = datetime.now(tz=tz.utc)
            sent_timezone = timezone or "UTC"
            msg = await _ChatMessageMixin.append_message(
                chat_id,
                "assistant",
                content,
                sent_at=sent_at,
                sent_timezone=sent_timezone,
                extra_data=extra_data,
                sibling_group_id=sibling_group_id,
            )
            await record_memory_influence_event(
                chat_id=chat_id,
                message_id=msg.id,
                content=content,
                extra_data=extra_data,
            )

            # Sync usage ledger to DB (O(1) dashboard querying)
            await sync_chat_usage(chat_id)

        except Exception as e:
            logger.error("Failed to persist assistant message for chat %s: %s", chat_id, e)
