"""compact_chat entry point.

[INPUT]
- compact.message_io::load_chat, load_compactable_messages (POS: incremental message slice)
- compact.llm_config::get_llm_for_user (POS: user model + window)
- compact.summarize_guard::guarded_compact_summarize (POS: progress timeout wrapper)
- compact.persist::do_persist_to_db, record_compaction_failure_cooldown (POS: DB writes)
- myrm_agent_harness...summarize_circuit_guard::is_summarize_circuit_open (POS: circuit breaker)
- myrm_agent_harness...compression_anti_thrash_guard (POS: streak guard + outcome record)
- compact._types::CompactReason, CompactResult (POS: closed decline reasons + outcome)

[OUTPUT]
- compact_chat: transactional compaction entry (``for_idle_stale`` idle predicate; ``request_tokens_for_guard`` aligns idle anti-thrash with gate; ``explicit_request`` marks a person's request, which the anti-thrash guard does not stop and which counts toward its streak only up to the guard limit)

[POS]
Server compaction orchestration; called by stale gate, /compact API, channel handler, idle worker.
"""

from __future__ import annotations

import asyncio
import logging

from myrm_agent_harness.utils.text_utils import get_token_count
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.chat.compact._lock import get_compaction_lock
from app.services.chat.compact._types import CompactReason, CompactResult
from app.services.chat.compact.idle_estimate import resolve_min_messages_to_compact
from app.services.chat.compact.llm_config import get_llm_for_user
from app.services.chat.compact.message_io import (
    backup_context,
    db_messages_to_langchain,
    load_chat,
    load_compactable_messages,
    parse_existing_summary,
)
from app.services.chat.compact.persist import (
    do_persist_to_db,
    record_compaction_failure_cooldown,
)
from app.services.chat.compact.summarize_guard import guarded_compact_summarize

logger = logging.getLogger(__name__)


async def compact_chat(
    db: AsyncSession,
    chat_id: str,
    *,
    focus_topic: str = "",
    for_idle_stale: bool = False,
    request_tokens_for_guard: int | None = None,
    explicit_request: bool = False,
) -> CompactResult:
    """Compact a chat's context by generating a persistent summary.

    The anti-thrash guard stops automatic attempts from repeating a compaction that keeps saving little, so it does not
    stop one a person asked for (``explicit_request``). That attempt still counts toward the guard's streak, but only up
    to the guard's limit: a person retrying never makes the chat look like its compaction is failing, which is what a
    streak beyond the limit reports.
    """
    lock = get_compaction_lock(chat_id)
    if lock.locked():
        logger.warning("⚠️ Compaction already in progress for chat %s, skipping.", chat_id)
        return CompactResult(compacted=False, reason=CompactReason.CONCURRENT_COMPACTION)

    async with lock:
        from myrm_agent_harness.agent.context_management.strategies.compression.compression_anti_thrash_guard import (
            ANTI_THRASHING_STREAK_LIMIT,
            record_compression_effectiveness,
            should_block_automatic_compression,
        )
        from myrm_agent_harness.agent.context_management.strategies.summary.summarize_circuit_guard import (
            is_summarize_circuit_open,
        )
        from myrm_agent_harness.utils.token_estimation import estimate_messages_tokens

        from app.services.chat.compact.compression_streak import (
            hydrate_compression_streak_from_db,
            save_compression_ineffective_streak,
        )

        if is_summarize_circuit_open():
            return CompactResult(compacted=False, reason=CompactReason.SUMMARIZE_CIRCUIT_OPEN)

        chat = await load_chat(db, chat_id)
        if chat is None:
            return CompactResult(compacted=False, reason=CompactReason.CHAT_NOT_FOUND)

        db_messages = await load_compactable_messages(db, chat)
        if for_idle_stale and not db_messages:
            return CompactResult(
                compacted=False,
                message_count=0,
                reason=CompactReason.NO_COMPACTABLE_MESSAGES,
            )
        if not for_idle_stale:
            min_messages = resolve_min_messages_to_compact(compacted_summary=chat.compacted_summary)
            if len(db_messages) < min_messages:
                logger.info(
                    "Compaction of chat %s skipped: %d messages, %d needed",
                    chat_id,
                    len(db_messages),
                    min_messages,
                )
                return CompactResult(
                    compacted=False,
                    message_count=len(db_messages),
                    reason=CompactReason.TOO_FEW_MESSAGES,
                )

        lc_messages = db_messages_to_langchain(db_messages)
        # The new summary replaces the stored one together with the messages after it. Counting only those messages
        # would make every incremental compaction look like it saved nothing, because the summary now carries both.
        original_tokens = estimate_messages_tokens(lc_messages)
        if chat.compacted_summary:
            original_tokens += get_token_count(chat.compacted_summary)

        existing_summary = parse_existing_summary(chat.compacted_summary) if chat.compacted_summary else None
        llm, max_context_tokens = await get_llm_for_user()

        await hydrate_compression_streak_from_db(db, chat_id)

        if not explicit_request:
            anti_thrash_tokens = original_tokens
            if for_idle_stale and request_tokens_for_guard is not None:
                anti_thrash_tokens = request_tokens_for_guard

            if should_block_automatic_compression(chat_id, anti_thrash_tokens, max_context_tokens):
                return CompactResult(
                    compacted=False,
                    original_tokens=original_tokens,
                    message_count=len(db_messages),
                    reason=CompactReason.ANTI_THRASH_ACTIVE,
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
                    reason=CompactReason.TIMEOUT,
                )
            await record_compaction_failure_cooldown(db, chat_id, str(summarize_exc))
            raise

        summary_tokens = get_token_count(summary.to_json())
        # A summary longer than what it replaces saved nothing; it is reported and recorded as zero, never as a loss.
        tokens_saved = max(original_tokens - summary_tokens, 0)

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
                streak_ceiling=ANTI_THRASHING_STREAK_LIMIT if explicit_request else None,
            )
            from myrm_agent_harness.agent.context_management.strategies.compression.compression_streak_store import (
                get_compression_streak_store,
            )

            await save_compression_ineffective_streak(
                db,
                chat_id,
                get_compression_streak_store().get_streak(chat_id),
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
                reason=CompactReason.PERSIST_FAILED,
            )
