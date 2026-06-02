"""Lossless context compaction service.

Generates a structured summary of older messages and persists it on the
Chat record.  Original messages are never deleted — the summary is used
by the Agent layer to reduce token cost while the UI continues to show
the full history.

Uses framework's generate_structured_summary for quality auditing
and incremental merging support.

[INPUT]
- database.models::Chat, Message (POS: ORM models for chat and message storage)
- myrm_agent_harness.utils.text_utils::get_token_count (POS: tiktoken-based token counting)
- myrm_agent_harness.toolkits.llms::llm_manager (POS: LLM instance factory, lazy)
- myrm_agent_harness.agent.context_management.strategies.summarizer::generate_structured_summary (POS: 框架层压缩核心)
- myrm_agent_harness.agent.context_management.infra.schemas::StructuredSummary (POS: 框架层摘要数据类)
- app.core.channel_bridge.config_loader::load_user_configs (POS: cached user config loader, lazy)
- app.platform_utils::get_storage_provider (POS: storage backend accessor, lazy)
- app.services.chat.conversation_recall_index_service::ConversationRecallIndexService (POS: Conversation Recall 索引生命周期服务)

[OUTPUT]
- compact_chat: async entry point — returns CompactResult (transactional)
- persist_compaction: SummaryPersistCallback implementation (fire-and-forget for Pipeline)
- _do_persist_to_db: core DB operation (shared by both paths)
- CompactResult: frozen dataclass describing compaction outcome

[POS]
Chat context compaction service.  Called by the /compact API endpoint,
by the IM router /compact command, and by the Pipeline's SummarizeProcessor
(via persist_compaction callback).  persist_compaction is the single source
of truth for writing compaction metadata to the Chat record.
compact_chat uses framework's generate_structured_summary for quality and consistency.
"""

from __future__ import annotations

import asyncio
import json
import logging
import weakref
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from myrm_agent_harness.utils.text_utils import get_token_count
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Chat, Message
from app.services.chat.conversation_recall_index_service import ConversationRecallIndexService

if TYPE_CHECKING:
    from langchain_core.language_models.chat_models import BaseChatModel
    from langchain_core.messages import BaseMessage
    from myrm_agent_harness.agent.context_management.infra.schemas import StructuredSummary

logger = logging.getLogger(__name__)

_MIN_MESSAGES_TO_COMPACT = 10
_compaction_locks: weakref.WeakValueDictionary[str, asyncio.Lock] = weakref.WeakValueDictionary()

def _get_compaction_lock(chat_id: str) -> asyncio.Lock:
    lock = _compaction_locks.get(chat_id)
    if lock is None:
        lock = asyncio.Lock()
        _compaction_locks[chat_id] = lock
    return lock


@dataclass(frozen=True, slots=True)
class CompactResult:
    """Outcome of a compaction attempt."""

    compacted: bool
    original_tokens: int = 0
    summary_tokens: int = 0
    tokens_saved: int = 0
    message_count: int = 0
    backup_path: str | None = None
    reason: str | None = None


async def _do_persist_to_db(
    db: AsyncSession,
    chat_id: str,
    summary_text: str,
    before_message_id: str,
    tokens_saved: int,
) -> str:
    """Execute the actual DB write for compaction metadata.

    Core DB operation shared by both persist_compaction (Pipeline fire-and-forget)
    and compact_chat (transactional). Does not commit — caller is responsible.

    Args:
        db: Active database session.
        chat_id: Target chat.
        summary_text: JSON-serialized StructuredSummary.
        before_message_id: DB ID of the last message covered by the summary.
        tokens_saved: Cumulative tokens saved by this compaction.

    Returns:
        Effective before_message_id (after fallback query if needed).

    Raises:
        ValueError: If chat_id is invalid or before_message_id cannot be resolved.
    """
    from sqlalchemy import desc

    effective_before_id: str | None = before_message_id or None
    if not effective_before_id:
        result = await db.execute(
            select(Message.id).where(Message.chat_id == chat_id).order_by(desc(Message.created_at)).limit(1)
        )
        effective_before_id = result.scalar_one_or_none()

    if not effective_before_id:
        raise ValueError(f"Cannot resolve before_message_id for chat_id={chat_id}")

    # Optimistic Concurrency Control: Check if DB already has a newer compaction boundary
    chat_result = await db.execute(select(Chat.compacted_before_id).where(Chat.id == chat_id))
    current_compacted_before_id = chat_result.scalar_one_or_none()

    if current_compacted_before_id and current_compacted_before_id != effective_before_id:
        ts_result = await db.execute(
            select(Message.id, Message.created_at)
            .where(Message.id.in_([current_compacted_before_id, effective_before_id]))
        )
        timestamps = {row[0]: row[1] for row in ts_result.all()}
        
        current_ts = timestamps.get(current_compacted_before_id)
        target_ts = timestamps.get(effective_before_id)
        
        if current_ts and target_ts and current_ts >= target_ts:
            logger.warning(
                "⚠️ [persist_compaction] DB has a newer or equal compaction boundary. Aborting overwrite."
            )
            return effective_before_id

    await db.execute(
        update(Chat)
        .where(Chat.id == chat_id)
        .values(
            compacted_summary=summary_text,
            compacted_before_id=effective_before_id,
            compacted_at=datetime.now(timezone.utc),
            compacted_tokens_saved=func.coalesce(Chat.compacted_tokens_saved, 0) + max(tokens_saved, 0),
        )
    )
    await db.flush()
    await ConversationRecallIndexService.rebuild_chat(db, chat_id)

    return effective_before_id


async def persist_compaction(
    chat_id: str,
    summary: object,
    before_message_id: str,
    tokens_saved: int,
) -> None:
    """Persist compaction metadata to the Chat record.

    This is the single source of truth for writing compaction data,
    shared by both Pipeline auto-summarize and the /compact command.

    Implements myrm_agent_harness's SummaryPersistCallback protocol.
    Creates a new DB session (for fire-and-forget async calls from Pipeline).

    Args:
        chat_id: Target chat.
        summary: StructuredSummary instance (from framework layer).
        before_message_id: DB ID of the last message covered by the summary.
            If empty, falls back to querying the latest message from DB.
        tokens_saved: Cumulative tokens saved by this compaction.
    """
    from app.database.connection import get_session

    summary_text: str
    if hasattr(summary, "to_json"):
        summary_text = summary.to_json()

    else:
        summary_text = str(summary)

    async with get_session() as db:
        try:
            effective_before_id = await _do_persist_to_db(db, chat_id, summary_text, before_message_id, tokens_saved)
            await db.commit()

            logger.warning(
                "💾 [persist_compaction] chat_id=%s, before_id=%s, tokens_saved=%d",
                chat_id,
                effective_before_id,
                tokens_saved,
            )
        except ValueError as exc:
            logger.warning("⚠️ [persist_compaction] %s", exc)
            await db.rollback()


async def compact_chat(
    db: AsyncSession,
    chat_id: str,
    *,
    focus_topic: str = "",
) -> CompactResult:
    """Compact a chat's context by generating a persistent summary.

    Uses framework's generate_structured_summary for quality auditing
    and incremental merging support.

    Args:
        db: Active database session.
        chat_id: Target chat.
        focus_topic: Optional topic to guide summarization focus.

    Returns:
        CompactResult describing what happened.
    """
    lock = _get_compaction_lock(chat_id)
    if lock.locked():
        logger.warning("⚠️ Compaction already in progress for chat %s, skipping.", chat_id)
        return CompactResult(compacted=False, reason="concurrent_compaction_in_progress")

    async with lock:
        from myrm_agent_harness.agent.context_management.strategies.summarizer import (
            generate_structured_summary,
        )
        from myrm_agent_harness.utils.token_estimation import (
            estimate_messages_tokens,
        )

        chat = await _load_chat(db, chat_id)
        if chat is None:
            return CompactResult(compacted=False, reason="chat_not_found")

        db_messages = await _load_compactable_messages(db, chat)
        if len(db_messages) < _MIN_MESSAGES_TO_COMPACT:
            return CompactResult(
                compacted=False,
                message_count=len(db_messages),
                reason=f"too_few_messages ({len(db_messages)} < {_MIN_MESSAGES_TO_COMPACT})",
            )

        lc_messages = _db_messages_to_langchain(db_messages)
        original_tokens = estimate_messages_tokens(lc_messages)

        existing_summary = _parse_existing_summary(chat.compacted_summary) if chat.compacted_summary else None
        llm = await _get_llm_for_user()

        _, summary = await generate_structured_summary(
            messages=lc_messages,
            llm=llm,
            user_id="sandbox",
            chat_id=chat_id,
            existing_summary=existing_summary,
            focus_topic=focus_topic,
        )

        summary_tokens = get_token_count(summary.to_json())
        tokens_saved = original_tokens - summary_tokens

        backup_path = await _backup_context(chat, db_messages)

        last_msg = db_messages[-1]

        try:
            await _do_persist_to_db(
                db=db,
                chat_id=chat_id,
                summary_text=summary.to_json(),
                before_message_id=last_msg.id,
                tokens_saved=tokens_saved,
            )
            await db.commit()

            logger.warning(
                "Chat %s compacted: %d messages → summary (%d tokens saved, backup: %s)",
                chat_id,
                len(db_messages),
                tokens_saved,
                backup_path,
            )

            return CompactResult(
                compacted=True,
                original_tokens=original_tokens,
                summary_tokens=summary_tokens,
                tokens_saved=tokens_saved,
                message_count=len(db_messages),
                backup_path=backup_path,
            )
        except ValueError as exc:
            await db.rollback()
            logger.error("Failed to persist compaction for chat %s: %s", chat_id, exc)
            return CompactResult(
                compacted=False,
                message_count=len(db_messages),
                reason=f"persist_failed: {exc}",
            )


# -- Internal helpers ----------------------------------------------------------


async def _load_chat(db: AsyncSession, chat_id: str) -> Chat | None:
    result = await db.execute(select(Chat).where(Chat.id == chat_id))
    return result.scalar_one_or_none()


async def _load_compactable_messages(db: AsyncSession, chat: Chat) -> list[Message]:
    """Load messages that should be included in compaction (incremental-aware)."""
    query = select(Message).where(Message.chat_id == chat.id)
    if chat.compacted_before_id:
        anchor = await db.execute(select(Message.created_at).where(Message.id == chat.compacted_before_id))
        anchor_ts = anchor.scalar_one_or_none()
        if anchor_ts:
            query = query.where(Message.created_at > anchor_ts)
    result = await db.execute(query.order_by(Message.created_at.asc()))
    return list(result.scalars().all())


def _db_messages_to_langchain(messages: list[Message]) -> list[BaseMessage]:
    """Convert DB Message records to LangChain message objects."""
    from langchain_core.messages import AIMessage, HumanMessage

    lc_messages: list[BaseMessage] = []
    for msg in messages:
        if msg.role == "user":
            lc_messages.append(HumanMessage(content=msg.content or ""))
        elif msg.role == "assistant":
            lc_messages.append(AIMessage(content=msg.content or ""))
    return lc_messages


def _parse_existing_summary(summary_json: str) -> StructuredSummary | None:
    """Parse JSON summary into StructuredSummary object."""
    from myrm_agent_harness.agent.context_management.infra.schemas import StructuredSummary

    try:
        summary_dict = json.loads(summary_json)
        return StructuredSummary(
            user_goal=summary_dict.get("user_goal", ""),
            completed_actions=summary_dict.get("completed_actions", []),
            key_findings=summary_dict.get("key_findings", []),
            files_modified=summary_dict.get("files_modified", []),
            last_action=summary_dict.get("last_action", ""),
        )
    except Exception:
        return None


async def _backup_context(
    chat: Chat,
    messages: list[Message],
) -> str | None:
    """Backup full context to workspace filesystem before compaction."""
    try:
        from app.platform_utils import get_storage_provider

        storage = get_storage_provider()

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        backup_path = f".myrm/chat_backups/{chat.id}/{timestamp}.jsonl"

        lines: list[str] = []
        if chat.compacted_summary:
            lines.append(json.dumps({"type": "previous_summary", "content": chat.compacted_summary}))
        for msg in messages:
            lines.append(
                json.dumps(
                    {
                        "id": msg.id,
                        "role": msg.role,
                        "content": msg.content,
                        "created_at": msg.created_at.isoformat() if msg.created_at else None,
                    }
                )
            )

        content = "\n".join(lines)
        await storage.write(backup_path, content.encode())
        return backup_path
    except Exception as exc:
        logger.warning("Context backup failed for chat %s: %s", chat.id, exc)
        return None


async def _get_llm_for_user() -> BaseChatModel:
    """Get LLM instance for user's configured model."""
    from myrm_agent_harness.toolkits.llms import llm_manager

    from app.core.channel_bridge.config_loader import load_user_configs

    configs = await load_user_configs()
    model_cfg = configs.model_cfg

    llm: BaseChatModel = await llm_manager.get_llm_from_config(
        model_cfg, streaming=False, api_keys=getattr(model_cfg, "api_keys", None)
    )
    return llm


async def get_archived_messages(chat_id: str) -> list[dict[str, object]]:
    """Retrieve all archived messages from the workspace backup files."""
    try:
        from app.platform_utils import get_storage_provider

        storage = get_storage_provider()
        prefix = f".myrm/chat_backups/{chat_id}/"

        # List all backup files for this chat
        files = await storage.list(prefix=prefix, recursive=False)

        all_messages: list[dict[str, object]] = []
        # Read files in chronological order (filename is timestamp)
        for file_path in sorted(files):
            content = await storage.read(file_path)
            if not content:
                continue
            lines = content.decode("utf-8").splitlines()
            for line in lines:
                if not line.strip():
                    continue
                try:
                    data_raw = json.loads(line)
                    if not isinstance(data_raw, dict):
                        continue
                    data: dict[str, object] = {str(k): v for k, v in data_raw.items()}
                    if data.get("type") == "previous_summary":
                        continue
                    all_messages.append(data)
                except Exception:
                    pass

        # Deduplicate by ID (in case multiple backups contain overlapping messages)
        seen_ids: set[object] = set()
        unique_messages: list[dict[str, object]] = []
        for msg in all_messages:
            msg_id = msg.get("id")
            if msg_id and msg_id not in seen_ids:
                seen_ids.add(msg_id)
                unique_messages.append(msg)

        return unique_messages
    except Exception as exc:
        logger.warning("Failed to retrieve archived messages for chat %s: %s", chat_id, exc)
        return []
