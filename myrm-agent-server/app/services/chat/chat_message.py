"""Message persistence mixin.

[INPUT]
- _base::_ChatServiceBase, _ChatRepositoryPort (POS: repository 协议和访问器)
- database.dto::MessageDTO (POS: 消息数据传输对象)
- chat_helpers::ALLOWED_MESSAGE_ROLES (POS: 合法消息角色集合)
- conversation_recall_index_service::ConversationRecallIndexService (POS: Conversation Recall 索引生命周期服务)

[OUTPUT]
- _ChatMessageMixin: 消息追加、分页查询、全量查询、assistant 消息安全持久化与记忆影响账本记录

[POS]
消息持久化编排层。提供消息追加（含自动 chat 元数据更新）、
分页查询、全量查询和 assistant 消息安全持久化（含用量同步与 memory_recall trace 投影）。
"""

from __future__ import annotations

import logging
from datetime import datetime
from uuid import uuid4

from myrm_agent_harness.toolkits.memory import MemoryInfluenceRef

from app.database.dto import ChatDTO, MessageDTO
from app.database.repositories.uow import UnitOfWork

from ._base import _ChatServiceBase
from .chat_helpers import ALLOWED_MESSAGE_ROLES
from .conversation_recall_index_service import ConversationRecallIndexService

logger = logging.getLogger(__name__)


class _ChatMessageMixin(_ChatServiceBase):
    """Message persistence operations."""

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
            from app.core.eval.service import mark_chat_activity

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
            await ConversationRecallIndexService.append_message(
                sess,
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
    ) -> MessageDTO:
        try:
            from app.core.eval.service import mark_chat_activity

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
                if field_updates:
                    await _ChatServiceBase._cr(uow).update_chat_fields(chat_id, field_updates)

            msg = MessageDTO(
                id=message_id or str(uuid4()),
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
            await ConversationRecallIndexService.append_message(
                sess,
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
    async def persist_assistant_message_safe(
        chat_id: str,
        content: str,
        extra_data: dict[str, object] | None = None,
        timezone: str | None = None,
        sibling_group_id: str | None = None,
    ) -> None:
        if not content.strip():
            return
        try:
            from datetime import timezone as tz

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
            await _record_memory_influence_event(
                chat_id=chat_id,
                message_id=msg.id,
                content=content,
                extra_data=extra_data,
            )

            # Sync usage ledger to DB (O(1) dashboard querying)
            try:
                from pathlib import Path

                from myrm_agent_harness.agent.event_log.analytics_queries import (
                    get_session_summary,
                )
                from myrm_agent_harness.agent.event_log.backends.file_backend import (
                    FileEventLogBackend,
                )

                from app.config.settings import settings

                event_log_file = Path(settings.database.event_log_dir) / f"{chat_id}.jsonl"
                if event_log_file.exists():
                    backend = FileEventLogBackend(
                        log_dir=Path(settings.database.event_log_dir),
                        session_id=chat_id,
                    )
                    summary = await get_session_summary(backend, session_id=chat_id, events_limit=150, timeline_limit=10)
                    if summary.token_economics:
                        usage_updates = {
                            "total_calls": summary.token_economics.get("call_count", 0),
                            "total_tokens": summary.token_economics.get("total_tokens", 0),
                            "total_usd": summary.token_economics.get("total_cost_usd", 0.0),
                        }
                        # update_chat_fields is in _ChatCrudMixin; use UnitOfWork directly
                        async with UnitOfWork() as uow:
                            await _ChatServiceBase._cr(uow).update_chat_fields(chat_id, usage_updates)
            except Exception as err:
                logger.error(f"Failed to sync usage ledger to DB for chat {chat_id}: {err}")

        except Exception as e:
            logger.error("Failed to persist assistant message for chat %s: %s", chat_id, e)


async def _record_memory_influence_event(
    *,
    chat_id: str,
    message_id: str,
    content: str,
    extra_data: dict[str, object] | None,
) -> None:
    if not extra_data:
        return
    refs = _memory_influence_refs(extra_data)
    traces = _memory_retrieval_traces(extra_data)
    if not refs and not traces:
        return
    try:
        from myrm_agent_harness.toolkits.memory import MemoryOperationKind, MemoryOperationStatus

        from app.database.connection import get_session
        from app.services.memory.operation_ledger import MemoryOperationLedgerService

        async with get_session() as db:
            ledger = MemoryOperationLedgerService(db)
            for trace in traces:
                trace_id = _optional_str(trace.get("id"))
                query_preview = _optional_str(trace.get("query_preview")) or ""
                result_count = _dict_int(trace, "result_count")
                for index, step in enumerate(_trace_steps(trace)):
                    phase = _optional_str(step.get("phase")) or "recall"
                    status_value = _optional_str(step.get("status"))
                    status = MemoryOperationStatus.SUCCESS
                    if status_value == "skipped":
                        status = MemoryOperationStatus.SKIPPED
                    elif status_value == "warning":
                        status = MemoryOperationStatus.WARNING
                    elif status_value == "error":
                        status = MemoryOperationStatus.ERROR
                    output_count = _dict_int(step, "output_count")
                    await ledger.record_event(
                        kind=MemoryOperationKind.RECALL,
                        status=status,
                        summary=str(step.get("summary") or step.get("title") or phase)[:240],
                        source="memory_retrieval_trace",
                        target_kind="chat",
                        target_id=chat_id,
                        correlation_id=message_id,
                        metadata={
                            "message_id": message_id,
                            "chat_id": chat_id,
                            "trace_id": trace_id,
                            "query_preview": query_preview[:180],
                            "step_index": index,
                            "step_phase": phase,
                            "step_title": str(step.get("title") or phase)[:80],
                            "output_count": output_count,
                            "result_count": result_count,
                            "duration_ms": _optional_float(step.get("duration_ms")),
                        },
                    )
            if refs:
                await ledger.record_event(
                    kind=MemoryOperationKind.CITE,
                    status=MemoryOperationStatus.SUCCESS,
                    summary=f"Assistant answer used {len(refs)} recalled memories: {content[:120]}",
                    source="agent_stream",
                    target_kind="chat",
                    target_id=chat_id,
                    correlation_id=message_id,
                    influence_refs=refs,
                    metadata={"message_id": message_id, "chat_id": chat_id, "influence_count": len(refs)},
                )
            await db.commit()
    except Exception as exc:
        logger.warning("Failed to record memory influence event for chat %s: %s", chat_id, exc)


def _memory_influence_refs(extra_data: dict[str, object]) -> list[MemoryInfluenceRef]:
    raw_refs = extra_data.get("citedMemoryRefs")
    if not isinstance(raw_refs, list):
        return []
    refs: list[MemoryInfluenceRef] = []
    for raw_ref in raw_refs:
        if not isinstance(raw_ref, dict):
            continue
        memory_id = raw_ref.get("id")
        memory_type = raw_ref.get("memory_type")
        if not isinstance(memory_id, str) or not isinstance(memory_type, str):
            continue
        raw_namespaces = raw_ref.get("namespaces")
        refs.append(
            MemoryInfluenceRef(
                memory_id=memory_id,
                memory_type=memory_type,
                score=_optional_float(raw_ref.get("score")),
                content_preview=str(raw_ref.get("content") or "")[:220],
                primary_namespace=_optional_str(raw_ref.get("primary_namespace")),
                namespaces=[str(item) for item in raw_namespaces if isinstance(item, str)]
                if isinstance(raw_namespaces, list)
                else [],
                source_chat_id=_optional_str(raw_ref.get("source_chat_id")),
                source_message_id=_optional_str(raw_ref.get("source_message_id")),
                reason="memory_search_tool",
            )
        )
    return refs


def _memory_retrieval_traces(extra_data: dict[str, object]) -> list[dict[str, object]]:
    raw_traces = extra_data.get("memoryRetrievalTraces")
    if not isinstance(raw_traces, list):
        return []
    traces: list[dict[str, object]] = []
    for raw_trace in raw_traces:
        if isinstance(raw_trace, dict):
            traces.append({str(key): value for key, value in raw_trace.items() if isinstance(key, str)})
    return traces


def _trace_steps(trace: dict[str, object]) -> list[dict[str, object]]:
    raw_steps = trace.get("steps")
    if not isinstance(raw_steps, list):
        return []
    steps: list[dict[str, object]] = []
    for raw_step in raw_steps:
        if isinstance(raw_step, dict):
            steps.append({str(key): value for key, value in raw_step.items() if isinstance(key, str)})
    return steps


def _optional_str(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _optional_float(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _dict_int(value: object, key: str) -> int:
    if not isinstance(value, dict):
        return 0
    raw = value.get(key)
    if isinstance(raw, bool):
        return 0
    if isinstance(raw, int):
        return max(raw, 0)
    if isinstance(raw, float):
        return max(int(raw), 0)
    return 0
