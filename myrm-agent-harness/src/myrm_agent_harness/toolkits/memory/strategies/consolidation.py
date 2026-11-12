"""Cross-session memory consolidation — retrospective reflection on accumulated memories.

[INPUT]
- memory.config::ConsolidationConfig (POS: consolidation configuration)
- memory._internal.store_stamp::settled_through (POS: arrival stamp of a stored memory and the writes still in flight)
- memory.manager::MemoryManager (POS: unified memory manager facade)
- strategies.bookkeeping::{read_bookkeeping, write_bookkeeping} (POS: Persistence of maintenance counters, hashes and timestamps)
- strategies.consolidation_models::* (POS: Domain models, DTOs, and protocol callback types for cross-session memory consolidation)
- strategies.consolidation_groups::{analyze_group, writable_groups} (POS: Namespace groups of a consolidation window, and the model's analysis of one group)
- strategies.consolidation_insights::persist_insights (POS: Insights a consolidation cycle draws: the closure check on what the model states, and their persistence)
- strategies.consolidation_ops_executor::execute_operations (POS: Executes operations against memory primitives with transactional care, conflict routing, and deterministic three-state merge arbitration)
- strategies.consolidation_undo::save_undo (POS: Exact undo of the latest consolidation cycle)
- strategies.consolidation_window::{enrich_with_similar, fetch_candidate_window} (POS: Oldest-first window of memories a consolidation run has not covered yet)

[OUTPUT]
- run_consolidation: Cross-session consolidation (contradiction detection, redundancy merge, insight generation)
- should_consolidate, get_last_consolidated_at: The time gate of a cycle and the covered-through timestamp it reads
- ConsolidationStats: Consolidation result statistics

[POS]
Cross-session memory consolidation: one cycle has the LLM analyze the oldest memories not yet covered, one namespace
group at a time, applies the merge/correct/update operations it proposes, persists the insights it draws, journals the
writes for undo and advances the covered-through stamp, and finishes those writes even when its caller is cancelled.
Triggered by end_session() and by a count of stored memories, both behind the interval gate, and by the maintenance
cycle, which the idle worker forces past it.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Coroutine, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from langchain_core.language_models import BaseChatModel

from myrm_agent_harness.toolkits.memory._internal.store_stamp import settled_through
from myrm_agent_harness.toolkits.memory.strategies.bookkeeping import read_bookkeeping, write_bookkeeping
from myrm_agent_harness.toolkits.memory.strategies.consolidation_groups import analyze_group, writable_groups
from myrm_agent_harness.toolkits.memory.strategies.consolidation_insights import persist_insights
from myrm_agent_harness.toolkits.memory.strategies.consolidation_models import (
    _PROFILE_KEY_LAST_CONSOLIDATED,
    ConflictCallback,
    ConflictContext,
    ConsolidationAction,
    ConsolidationBatch,
    ConsolidationCompleteCallback,
    ConsolidationOp,
    ConsolidationResponse,
    ConsolidationStats,
    CorrectOp,
    MergeOp,
    UndoJournal,
    UpdateContentOp,
)
from myrm_agent_harness.toolkits.memory.strategies.consolidation_ops_executor import execute_operations
from myrm_agent_harness.toolkits.memory.strategies.consolidation_undo import save_undo
from myrm_agent_harness.toolkits.memory.strategies.consolidation_window import (
    enrich_with_similar,
    fetch_candidate_window,
)

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.memory.config import ConsolidationConfig
    from myrm_agent_harness.toolkits.memory.manager import MemoryManager

logger = logging.getLogger(__name__)


async def get_last_consolidated_at(manager: MemoryManager) -> datetime | None:
    """Read the covered-through timestamp from the manager's bookkeeping row.

    The timestamp is a store stamp, and a stamp can run ahead of the wall clock while the wall clock catches up
    after a step back. A stored value that cannot be parsed, is naive or is ahead of the wall clock is ignored, with a
    warning, so it cannot make the time gates raise or hold consolidation back indefinitely; the next run then starts
    again from the oldest memories.
    """
    if not manager.has_relational:
        return None
    raw = await read_bookkeeping(manager, _PROFILE_KEY_LAST_CONSOLIDATED)
    if not raw:
        return None
    try:
        last = datetime.fromisoformat(raw)
    except (ValueError, TypeError):
        logger.warning("Consolidation covered-through stamp %r cannot be parsed; ignored", raw)
        return None
    if last.tzinfo is None or last > datetime.now(UTC):
        logger.warning("Consolidation covered-through stamp %s is naive or ahead of the wall clock; ignored", raw)
        return None
    return last


async def should_consolidate(manager: MemoryManager, config: ConsolidationConfig) -> bool:
    """Check whether consolidation should run based on time gates."""
    if not config.enabled:
        return False
    last = await get_last_consolidated_at(manager)
    if last is None:
        return True
    elapsed_hours = (datetime.now(UTC) - last).total_seconds() / 3600
    return elapsed_hours >= config.interval_hours


async def run_consolidation(
    manager: MemoryManager,
    llm: BaseChatModel,
    config: ConsolidationConfig,
    *,
    on_conflict: ConflictCallback | None = None,
    on_complete: ConsolidationCompleteCallback | None = None,
) -> ConsolidationStats:
    """Execute one consolidation cycle over the oldest memories not covered yet."""
    start = datetime.now(UTC)

    last = await get_last_consolidated_at(manager)
    if last is not None:
        elapsed_hours = (datetime.now(UTC) - last).total_seconds() / 3600
        if elapsed_hours < config.soft_lock_hours:
            logger.info(
                "Consolidation skipped: soft lock (%.1fh < %.1fh)",
                elapsed_hours,
                config.soft_lock_hours,
            )
            return ConsolidationStats()

    window = await fetch_candidate_window(manager, last, config.max_memories, settled_through())
    new_ids: frozenset[str] | None = None

    enriched_count = 0
    if len(window.memories) == 1:
        new_ids = frozenset(m.id for m in window.memories)
        memories = await enrich_with_similar(window.memories[0], manager, max_similar=config.enrich_max_similar)
        enriched_count = len(memories) - 1
    else:
        memories = window.memories

    groups = writable_groups(memories, manager, new_ids)
    if not groups:
        logger.info("Consolidation skipped: no namespace group is worth a model call (%d memories)", len(memories))
        await _advance_stamp(manager, window.advance_to)
        return ConsolidationStats()

    input_count = sum(len(group) for group in groups)
    today = start.strftime("%Y-%m-%d")
    try:
        batches = [await analyze_group(group, llm, today, new_ids) for group in groups]
    except Exception as e:
        logger.warning("Consolidation LLM call failed: %s", e)
        return ConsolidationStats(errors=1, input_count=input_count, enriched_count=enriched_count)

    if not any(batch.operations or batch.insights for batch in batches):
        rejected = sum(batch.rejected for batch in batches)
        logger.info(
            "Consolidation: no operations needed (input=%d, enriched=%d, rejected=%d)",
            input_count,
            enriched_count,
            rejected,
        )
        await _advance_stamp(manager, window.advance_to)
        empty_stats = ConsolidationStats(input_count=input_count, enriched_count=enriched_count, rejected=rejected)
        if on_complete is not None:
            try:
                await on_complete(empty_stats)
            except Exception as exc:
                logger.warning("Consolidation complete hook failed (non-fatal): %s", exc)
        return empty_stats

    answer = _Answer(batches=batches, advance_to=window.advance_to, started=start, enriched_count=enriched_count)
    return await _run_to_completion(_apply(manager, answer, config, on_conflict, on_complete))


@dataclass(frozen=True, slots=True)
class _Answer:
    """What the model answered for every group of one window, with everything that writing it needs."""

    batches: Sequence[ConsolidationBatch]
    advance_to: datetime | None
    started: datetime
    enriched_count: int


async def _apply(
    manager: MemoryManager,
    answer: _Answer,
    config: ConsolidationConfig,
    on_conflict: ConflictCallback | None,
    on_complete: ConsolidationCompleteCallback | None,
) -> ConsolidationStats:
    """Write the answer: its operations and insights, the undo journal and the covered-through stamp."""
    batches = answer.batches
    input_count = sum(len(batch.memories) for batch in batches)
    stats = (
        await execute_operations(batches, manager, on_conflict=on_conflict, config=config)
        if any(batch.operations for batch in batches)
        else ConsolidationStats()
    )
    elapsed_ms = (datetime.now(UTC) - answer.started).total_seconds() * 1000
    stats.duration_ms = elapsed_ms
    stats.input_count = input_count
    stats.enriched_count = answer.enriched_count
    stats.guard_patched = sum(batch.guard_patched for batch in batches)
    stats.rejected += sum(batch.rejected for batch in batches)

    # A cycle that only adds insights changes no existing memory, so it must not take the undo slot from an earlier
    # cycle that did.
    insight_journal = stats.undo if stats.undo.change_count else UndoJournal()
    stored_insights: list[str] = []
    for batch in batches:
        if batch.insights:
            stored_insights += await persist_insights(manager, batch.insights, batch.memories, insight_journal)
    # The summary and the completion hook report the insights the store took, not every one the model proposed.
    stats.insights = tuple(stored_insights)
    await save_undo(manager, stats)

    should_advance_timestamp = not stats.aborted and not (
        stats.errors > 0 and (stats.merged + stats.corrected + stats.updated == 0)
    )
    if should_advance_timestamp:
        await _advance_stamp(manager, answer.advance_to)
    else:
        logger.warning(
            "Consolidation skipped timestamp advancement (aborted=%s, errors=%d)",
            stats.aborted,
            stats.errors,
        )

    logger.info(
        "Consolidation complete: input=%d, enriched=%d, merged=%d, corrected=%d, updated=%d, errors=%d, "
        "guard_patched=%d, rejected=%d, insights=%d (%.0fms)",
        input_count,
        answer.enriched_count,
        stats.merged,
        stats.corrected,
        stats.updated,
        stats.errors,
        stats.guard_patched,
        stats.rejected,
        len(stats.insights),
        elapsed_ms,
    )
    if on_complete is not None:
        try:
            await on_complete(stats)
        except Exception as exc:
            logger.warning("Consolidation complete hook failed (non-fatal): %s", exc)
    return stats


async def _run_to_completion(work: Coroutine[None, None, ConsolidationStats]) -> ConsolidationStats:
    """Await ``work`` without letting a cancel of the caller interrupt it; the cancel is delivered once ``work`` is done.

    The idle worker cancels a running cycle when the user's next turn ends. A cycle cut off between its writes would
    leave merges half applied, with no undo journal and no covered-through stamp, so the next cycle would read the same
    memories again and merge them a second time. Holding the caller until the writes are done also keeps its maintenance
    lock, so a cycle triggered meanwhile is turned away instead of merging the same memories.
    """
    task = asyncio.create_task(work)
    cancelled = False
    while not task.done():
        try:
            await asyncio.wait({task})
        except asyncio.CancelledError:
            cancelled = True
    if not cancelled:
        return task.result()
    if not task.cancelled() and (error := task.exception()) is not None:
        logger.error("Consolidation apply failed while its caller was being cancelled: %r", error)
    raise asyncio.CancelledError


async def _advance_stamp(manager: MemoryManager, advance_to: datetime | None) -> None:
    """Persist the covered-through stamp; ``None`` means a source was unreadable, so the stamp stays put."""
    if advance_to is None or not manager.has_relational:
        return
    try:
        await write_bookkeeping(manager, _PROFILE_KEY_LAST_CONSOLIDATED, advance_to.isoformat())
    except Exception as e:
        logger.warning("Failed to update consolidation timestamp: %s", e)


__all__ = [
    "ConflictCallback",
    "ConflictContext",
    "ConsolidationAction",
    "ConsolidationCompleteCallback",
    "ConsolidationOp",
    "ConsolidationResponse",
    "ConsolidationStats",
    "CorrectOp",
    "MergeOp",
    "UpdateContentOp",
    "execute_operations",
    "get_last_consolidated_at",
    "run_consolidation",
    "should_consolidate",
]
