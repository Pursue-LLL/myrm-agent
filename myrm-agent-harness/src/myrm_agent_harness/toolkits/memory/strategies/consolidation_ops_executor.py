"""Atomic operation execution for memory consolidation.

[INPUT]
- memory.manager::MemoryManager (POS: unified memory manager facade)
- memory.config::ConsolidationConfig (POS: consolidation configuration)
- strategies.consolidation_gate::{GateRefusal, admit} (POS: apply-time check that a memory is still what the model read)
- strategies.consolidation_models::* (POS: consolidation operations and data contracts)
- strategies.consolidation_product::build_merge_product (POS: the memory a merge creates, with the scope and age it inherits)
- strategies.consolidation_undo::CycleWrites (POS: the write gateway that journals what a cycle changes)
- strategies.merger::{DeterministicThreeStateMerger, MergeState} (POS: deterministic three-state arbitration of a correction)

[OUTPUT]
- execute_operations: Executes the atomic merge/correct/update operations of each namespace group against memory storage

[POS]
Executes operations against memory primitives with transactional care, conflict routing,
and deterministic three-state merge arbitration. Every write goes through the cycle's write gateway,
so what the cycle changed is journaled for undo, and an operation acts on a memory only while the store's copy
still passes the gate: a source that was deleted (its chat included), archived, edited, pinned or already folded
into an earlier merge is skipped, never folded or overwritten.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

from myrm_agent_harness.toolkits.memory._internal.storage import MemoryProtectedError
from myrm_agent_harness.toolkits.memory.strategies.consolidation_gate import GateRefusal, admit
from myrm_agent_harness.toolkits.memory.strategies.consolidation_models import (
    CONSOLIDATED_FLAG_KEY,
    ConflictCallback,
    ConflictContext,
    ConsolidationBatch,
    ConsolidationOp,
    ConsolidationStats,
    CorrectOp,
    MergeOp,
    UpdateContentOp,
)
from myrm_agent_harness.toolkits.memory.strategies.consolidation_product import build_merge_product
from myrm_agent_harness.toolkits.memory.strategies.consolidation_undo import CycleWrites
from myrm_agent_harness.toolkits.memory.strategies.merger import (
    DeterministicThreeStateMerger,
    MergeState,
)
from myrm_agent_harness.toolkits.memory.types import ConflictResolution, MemoryType, SemanticMemory

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.memory.config import ConsolidationConfig
    from myrm_agent_harness.toolkits.memory.manager import MemoryManager

logger = logging.getLogger(__name__)

_MAX_CONSECUTIVE_ERRORS = 3
# A merged source stays stored (the cycle can be undone) but ranks far below its product.
_FOLDED_SOURCE_IMPORTANCE = 0.05


@dataclass(slots=True)
class _Cycle:
    """What every operation of one cycle shares."""

    manager: MemoryManager
    writes: CycleWrites
    stats: ConsolidationStats
    on_conflict: ConflictCallback | None
    importance_threshold: float
    confidence_threshold: float


def _skipped(stats: ConsolidationStats, refusals: Mapping[str, GateRefusal]) -> None:
    """Count one operation the gate turned away, naming the memories it refused and why (never their content)."""
    stats.rejected += 1
    logger.info(
        "Consolidation op skipped by the gate: %s",
        ", ".join(f"{memory_id} ({reason})" for memory_id, reason in refusals.items()),
    )


async def _merge(cycle: _Cycle, op: MergeOp, seen: Mapping[str, str]) -> None:
    fetched = await asyncio.gather(*(cycle.manager.get_memory(source_id) for source_id in op.source_ids))
    admitted = [admit(memory, seen[source_id]) for source_id, memory in zip(op.source_ids, fetched, strict=True)]
    if refusals := {
        source_id: result
        for source_id, result in zip(op.source_ids, admitted, strict=True)
        if isinstance(result, GateRefusal)
    }:
        _skipped(cycle.stats, refusals)
        return
    sources = [result for result in admitted if not isinstance(result, GateRefusal)]
    await cycle.writes.store(build_merge_product(op, sources))
    for source_id in op.source_ids:
        try:
            await cycle.writes.update_memory(
                source_id, importance=_FOLDED_SOURCE_IMPORTANCE, metadata_patch={CONSOLIDATED_FLAG_KEY: True}
            )
        except MemoryProtectedError:
            logger.info("Consolidation demote skipped protected memory %s", source_id)
        except Exception as e:
            logger.warning("Consolidation demote failed for %s: %s", source_id, e)
    cycle.stats.merged += 1


async def _correct(cycle: _Cycle, op: CorrectOp, seen: Mapping[str, str]) -> None:
    memory_id = op.memory_id
    existing = admit(await cycle.manager.get_memory(memory_id), seen[memory_id])
    if isinstance(existing, GateRefusal):
        _skipped(cycle.stats, {memory_id: existing})
        return
    stats, writes, on_conflict = cycle.stats, cycle.writes, cycle.on_conflict

    if (
        on_conflict is not None
        and op.importance >= cycle.importance_threshold
        and op.accuracy_score < cycle.confidence_threshold
    ):
        ctx = ConflictContext(
            old_memory_id=memory_id,
            old_content=getattr(existing, "content", ""),
            new_content=op.corrected_content,
            accuracy_score=op.accuracy_score,
            importance=op.importance,
            merge_suggestion=op.corrected_content,
            memory_type=getattr(existing, "memory_type", MemoryType.SEMANTIC),
        )
        resolution = await on_conflict(ctx)
        if resolution == ConflictResolution.PENDING:
            stats.routed_to_user += 1
            return
        if resolution == ConflictResolution.KEEP_OLD:
            return
        if resolution == ConflictResolution.DISCARD_BOTH:
            await writes.update_memory(memory_id, importance=0.01)
            stats.corrected += 1
            return
        # KEEP_NEW or MERGE: proceed to execute the correction below

    decision = DeterministicThreeStateMerger().evaluate(
        existing=existing,
        candidate_content=op.corrected_content,
        candidate_evidence=getattr(existing, "evidence", []),
    )

    if decision.state == MergeState.CONFLICT:
        logger.info("Consolidation: conflict detected for %s; retaining both with decayed confidence", memory_id)
        if isinstance(existing, SemanticMemory):
            await writes.update_memory(memory_id, confidence=decision.updated_confidence or 0.35)
            counterpart = SemanticMemory(
                content=op.corrected_content,
                importance=op.importance,
                confidence=decision.candidate_confidence or 0.35,
                scope=existing.scope,
                source_chat_id=existing.source_chat_id,
                source_chat_ids=list(existing.source_chat_ids),
            )
            await writes.store(counterpart)
            stats.updated += 1
            return

    if decision.state == MergeState.CONFIRM:
        if isinstance(existing, SemanticMemory) and decision.updated_confidence is not None:
            await writes.update_memory(memory_id, confidence=decision.updated_confidence)
        stats.updated += 1
        return

    if decision.state == MergeState.SUPPLEMENT and decision.merged_content:
        await writes.update_memory(memory_id, content=decision.merged_content)
        stats.updated += 1
        return

    if isinstance(existing, SemanticMemory):
        await writes.correct_memory(memory_id, op.corrected_content)
        stats.corrected += 1
    else:
        await writes.update_memory(memory_id, content=op.corrected_content)
        stats.updated += 1


async def _update(cycle: _Cycle, op: UpdateContentOp, seen: Mapping[str, str]) -> None:
    admitted = admit(await cycle.manager.get_memory(op.memory_id), seen[op.memory_id])
    if isinstance(admitted, GateRefusal):
        _skipped(cycle.stats, {op.memory_id: admitted})
        return
    await cycle.writes.update_memory(op.memory_id, content=op.new_content, importance=op.importance)
    cycle.stats.updated += 1


async def execute_operations(
    batches: Sequence[ConsolidationBatch],
    manager: MemoryManager,
    *,
    on_conflict: ConflictCallback | None = None,
    config: ConsolidationConfig | None = None,
) -> ConsolidationStats:
    """Execute the batches' atomic consolidation operations against the memory store, journaling them as one cycle."""
    planned: list[tuple[ConsolidationOp, Mapping[str, str]]] = []
    for batch in batches:
        read_by_model = {memory.id: memory.content for memory in batch.memories}
        planned.extend((op, read_by_model) for op in batch.operations)

    stats = ConsolidationStats(total_processed=len(planned))
    cycle = _Cycle(
        manager=manager,
        writes=CycleWrites(manager, stats.undo),
        stats=stats,
        on_conflict=on_conflict,
        importance_threshold=config.conflict_importance_threshold if config else 0.6,
        confidence_threshold=config.conflict_confidence_threshold if config else 0.85,
    )
    consecutive_errors = 0

    for op, seen in planned:
        failed_with_exception = False
        try:
            if isinstance(op, MergeOp):
                await _merge(cycle, op, seen)
            elif isinstance(op, CorrectOp):
                await _correct(cycle, op, seen)
            else:
                await _update(cycle, op, seen)
        except MemoryProtectedError:
            stats.rejected += 1
            logger.info("Consolidation op skipped: the memory is user-protected")
        except Exception as e:
            failed_with_exception = True
            logger.warning("Consolidation op failed: %s: %s", type(e).__name__, e)
            stats.errors += 1
            consecutive_errors += 1
            if consecutive_errors >= _MAX_CONSECUTIVE_ERRORS:
                logger.error(
                    "Consolidation aborted: consecutive errors reached threshold (%d)",
                    _MAX_CONSECUTIVE_ERRORS,
                )
                stats.aborted = True
                break
        finally:
            if not failed_with_exception:
                consecutive_errors = 0

    return stats


__all__ = ["execute_operations"]
