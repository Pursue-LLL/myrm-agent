"""compact_chat entry point.

[INPUT]
- compact.message_io::load_chat, load_compactable_messages (POS: incremental message slice)
- compact.llm_config::get_llm_for_user (POS: user model + window)
- compact.summarize_guard::guarded_compact_summarize (POS: progress timeout wrapper)
- compact.persist::do_persist_to_db, record_compaction_failure_cooldown (POS: DB writes)
- myrm_agent_harness...summarize_circuit_guard::is_summarize_circuit_open (POS: circuit breaker)
- myrm_agent_harness...compression_anti_thrash_guard (POS: streak guard + outcome record)

[OUTPUT]
- compact_chat: transactional compaction entry (``for_idle_stale`` Hermes idle predicate; ``request_tokens_for_guard`` aligns idle anti-thrash with gate)

[POS]
Server compaction orchestration; called by stale gate, /compact API, channel handler, idle worker.
"""

from __future__ import annotations

import asyncio
import logging

from myrm_agent_harness.utils.text_utils import get_token_count
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.chat.compact._lock import get_compaction_lock
from app.services.chat.compact._types import CompactResult
from app.services.chat.compact.idle_estimate import resolve_min_messages_to_compact
from app.services.chat.compact.llm_config import get_llm_for_user
from app.services.chat.compact.message_io import (
    backup_context,
    db_messages_to_langchain,
    load_chat,
    load_compactable_messages,
    parse_existing_summary,
)
from app.services.chat.compact.persist import do_persist_to_db, record_compaction_failure_cooldown
from app.services.chat.compact.summarize_guard import guarded_compact_summarize

logger = logging.getLogger(__name__)


async def compact_chat(
    db: AsyncSession,
    chat_id: str,
    *,
    focus_topic: str = "",
    for_idle_stale: bool = False,
    request_tokens_for_guard: int | None = None,
) -> CompactResult:
    """Compact a chat's context by generating a persistent summary."""
    lock = get_compaction_lock(chat_id)
    if lock.locked():
        logger.warning("⚠️ Compaction already in progress for chat %s, skipping.", chat_id)
        return CompactResult(compacted=False, reason="concurrent_compaction_in_progress")

    async with lock:
        from myrm_agent_harness.agent.context_management.strategies.compression_anti_thrash_guard import (
            record_compression_effectiveness,
            should_block_automatic_compression,
        )
        from myrm_agent_harness.agent.context_management.strategies.summarize_circuit_guard import (
            is_summarize_circuit_open,
        )
        from myrm_agent_harness.utils.token_estimation import estimate_messages_tokens

        if is_summarize_circuit_open():
            return CompactResult(compacted=False, reason="summarize_circuit_open")

        chat = await load_chat(db, chat_id)
        if chat is None:
            return CompactResult(compacted=False, reason="chat_not_found")

        db_messages = await load_compactable_messages(db, chat)
        if for_idle_stale and not db_messages:
            return CompactResult(
                compacted=False,
                message_count=0,
                reason="no_compactable_messages",
            )
        if not for_idle_stale:
            min_messages = resolve_min_messages_to_compact(compacted_summary=chat.compacted_summary)
            if len(db_messages) < min_messages:
                return CompactResult(
                    compacted=False,
                    message_count=len(db_messages),
                    reason=f"too_few_messages ({len(db_messages)} < {min_messages})",
                )

        lc_messages = db_messages_to_langchain(db_messages)
        original_tokens = estimate_messages_tokens(lc_messages)

        existing_summary = parse_existing_summary(chat.compacted_summary) if chat.compacted_summary else None
        llm, max_context_tokens = await get_llm_for_user()

        anti_thrash_tokens = original_tokens
        if for_idle_stale and request_tokens_for_guard is not None:
            anti_thrash_tokens = request_tokens_for_guard

        if should_block_automatic_compression(chat_id, anti_thrash_tokens, max_context_tokens):
            return CompactResult(
                compacted=False,
                original_tokens=original_tokens,
                message_count=len(db_messages),
                reason="compression_anti_thrash_active",
            )

        try:
            _, summary = await guarded_compact_summarize(
                lc_messages=lc_messages,
                llm=llm,
                chat_id=chat_id,
                existing_summary=existing_summary,
                focus_topic=focus_topic,
                max_context_tokens=max_context_tokens,
            )
        except (asyncio.TimeoutError, Exception) as summarize_exc:
            if isinstance(summarize_exc, asyncio.TimeoutError):
                await record_compaction_failure_cooldown(
                    db,
                    chat_id,
                    f"timeout: {summarize_exc}",
                )
                return CompactResult(
                    compacted=False,
                    original_tokens=original_tokens,
                    message_count=len(db_messages),
                    reason=f"timeout: {summarize_exc}",
                )
            await record_compaction_failure_cooldown(db, chat_id, str(summarize_exc))
            raise

        summary_tokens = get_token_count(summary.to_json())
        tokens_saved = original_tokens - summary_tokens

        backup_path = await backup_context(chat, db_messages)

        last_msg = db_messages[-1]

        try:
            await do_persist_to_db(
                db=db,
                chat_id=chat_id,
                summary_text=summary.to_json(),
                before_message_id=last_msg.id,
                tokens_saved=tokens_saved,
            )
            await db.commit()

            record_compression_effectiveness(
                chat_id,
                original_tokens=original_tokens,
                tokens_saved=tokens_saved,
            )

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
            await record_compaction_failure_cooldown(db, chat_id, f"persist_failed: {exc}")
            await db.commit()
            logger.error("Failed to persist compaction for chat %s: %s", chat_id, exc)
            return CompactResult(
                compacted=False,
                message_count=len(db_messages),
                reason=f"persist_failed: {exc}",
            )
