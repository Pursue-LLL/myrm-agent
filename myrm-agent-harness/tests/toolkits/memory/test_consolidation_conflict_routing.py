"""Tests for consolidation conflict routing in execute_operations.

Covers:
- CorrectOp routing decision: importance_thr / confidence_thr gates
- Each ConflictResolution branch: PENDING, KEEP_OLD, KEEP_NEW, MERGE, DISCARD_BOTH
- ConsolidationStats.routed_to_user counter
- Default thresholds when config is None
- Custom thresholds from ConsolidationConfig
"""

from __future__ import annotations

from collections.abc import Sequence
from unittest.mock import AsyncMock

import pytest

from myrm_agent_harness.toolkits.memory.config import ConsolidationConfig
from myrm_agent_harness.toolkits.memory.strategies.consolidation import (
    ConflictCallback,
    ConflictContext,
    ConsolidationOp,
    ConsolidationStats,
    CorrectOp,
    MergeOp,
    execute_operations,
)
from myrm_agent_harness.toolkits.memory.types import (
    AnyMemory,
    ConflictResolution,
    EpisodicMemory,
    MemoryType,
    ProceduralMemory,
    SemanticMemory,
)
from tests.support.consolidation_manager import batches_of, make_manager_serving


def _named(op: ConsolidationOp) -> list[str]:
    return list(op.source_ids) if isinstance(op, MergeOp) else [op.memory_id]


async def _run(
    ops: Sequence[ConsolidationOp],
    *,
    store: Sequence[AnyMemory] | None = None,
    on_conflict: ConflictCallback | None = None,
    config: ConsolidationConfig | None = None,
) -> tuple[ConsolidationStats, AsyncMock]:
    """Execute ``ops`` against a store holding what the model read: ``store``, else one plain memory per named id."""
    names = sorted({name for op in ops for name in _named(op)})
    memories = list(store) if store is not None else [SemanticMemory(id=name, content="old content") for name in names]
    manager = make_manager_serving(*memories)
    stats = await execute_operations(batches_of(memories, *ops), manager, on_conflict=on_conflict, config=config)
    return stats, manager


class TestConflictRoutingDecision:
    """Tests the should_route gate: importance >= threshold AND accuracy < threshold."""

    @pytest.mark.asyncio
    async def test_no_callback_skips_routing(self) -> None:
        """Without on_conflict, corrections execute directly."""
        ops = [CorrectOp(memory_id="mem-1", corrected_content="new", importance=0.9, accuracy_score=0.5)]
        stats, _ = await _run(ops, on_conflict=None)
        assert stats.routed_to_user == 0
        assert stats.corrected == 1

    @pytest.mark.asyncio
    async def test_low_importance_skips_routing(self) -> None:
        """importance < threshold → direct correction, no routing."""
        callback = AsyncMock(return_value=ConflictResolution.PENDING)
        ops = [CorrectOp(memory_id="mem-1", corrected_content="new", importance=0.3, accuracy_score=0.5)]
        stats, _ = await _run(ops, on_conflict=callback)
        callback.assert_not_called()
        assert stats.corrected == 1

    @pytest.mark.asyncio
    async def test_high_accuracy_skips_routing(self) -> None:
        """accuracy >= threshold → confident correction, no routing."""
        callback = AsyncMock(return_value=ConflictResolution.PENDING)
        ops = [CorrectOp(memory_id="mem-1", corrected_content="new", importance=0.9, accuracy_score=0.95)]
        stats, _ = await _run(ops, on_conflict=callback)
        callback.assert_not_called()
        assert stats.corrected == 1

    @pytest.mark.asyncio
    async def test_triggers_routing(self) -> None:
        """importance >= 0.6 AND accuracy < 0.85 → routes to callback."""
        callback = AsyncMock(return_value=ConflictResolution.PENDING)
        ops = [CorrectOp(memory_id="mem-1", corrected_content="new", importance=0.8, accuracy_score=0.6)]
        stats, _ = await _run(ops, on_conflict=callback)
        callback.assert_called_once()
        assert stats.routed_to_user == 1
        assert stats.corrected == 0

    @pytest.mark.asyncio
    async def test_routing_preserves_memory_type(self) -> None:
        """ConflictContext.memory_type reflects the conflicting memory's real type (not hardcoded)."""
        callback = AsyncMock(return_value=ConflictResolution.PENDING)
        ops = [CorrectOp(memory_id="mem-1", corrected_content="new", importance=0.8, accuracy_score=0.6)]
        stats, _ = await _run(ops, store=[EpisodicMemory(id="mem-1", content="old event")], on_conflict=callback)
        callback.assert_called_once()
        ctx = callback.call_args[0][0]
        assert ctx.memory_type == MemoryType.EPISODIC
        assert stats.routed_to_user == 1


class TestConflictResolutionBranches:
    """Tests each ConflictResolution outcome from the callback."""

    @pytest.mark.asyncio
    async def test_pending_skips_execution(self) -> None:
        callback = AsyncMock(return_value=ConflictResolution.PENDING)
        ops = [CorrectOp(memory_id="mem-1", corrected_content="new", importance=0.8, accuracy_score=0.5)]
        stats, manager = await _run(ops, on_conflict=callback)
        assert stats.routed_to_user == 1
        assert stats.corrected == 0
        manager.correct_memory.assert_not_called()
        manager.update_memory.assert_not_called()

    @pytest.mark.asyncio
    async def test_keep_old_skips_execution(self) -> None:
        callback = AsyncMock(return_value=ConflictResolution.KEEP_OLD)
        ops = [CorrectOp(memory_id="mem-1", corrected_content="new", importance=0.8, accuracy_score=0.5)]
        stats, manager = await _run(ops, on_conflict=callback)
        assert stats.routed_to_user == 0
        assert stats.corrected == 0
        manager.correct_memory.assert_not_called()

    @pytest.mark.asyncio
    async def test_keep_new_executes_correction(self) -> None:
        callback = AsyncMock(return_value=ConflictResolution.KEEP_NEW)
        ops = [CorrectOp(memory_id="mem-1", corrected_content="new", importance=0.8, accuracy_score=0.5)]
        stats, manager = await _run(ops, on_conflict=callback)
        assert stats.corrected == 1
        manager.correct_memory.assert_called_once()

    @pytest.mark.asyncio
    async def test_merge_executes_correction(self) -> None:
        callback = AsyncMock(return_value=ConflictResolution.MERGE)
        ops = [CorrectOp(memory_id="mem-1", corrected_content="merged", importance=0.8, accuracy_score=0.5)]
        stats, manager = await _run(ops, on_conflict=callback)
        assert stats.corrected == 1
        manager.correct_memory.assert_called_once()

    @pytest.mark.asyncio
    async def test_discard_both_demotes(self) -> None:
        callback = AsyncMock(return_value=ConflictResolution.DISCARD_BOTH)
        ops = [CorrectOp(memory_id="mem-1", corrected_content="new", importance=0.8, accuracy_score=0.5)]
        stats, manager = await _run(ops, on_conflict=callback)
        assert stats.corrected == 1
        manager.update_memory.assert_called_once_with(
            "mem-1", importance=0.01, confidence=None, content=None, metadata=None, allow_protected=False
        )
        manager.correct_memory.assert_not_called()


class TestConflictCallbackContext:
    """Verifies the ConflictContext passed to the callback has correct values."""

    @pytest.mark.asyncio
    async def test_context_fields(self) -> None:
        captured_ctx: list[ConflictContext] = []

        async def capture_callback(ctx: ConflictContext) -> ConflictResolution:
            captured_ctx.append(ctx)
            return ConflictResolution.PENDING

        ops = [
            CorrectOp(
                memory_id="mem-1",
                corrected_content="new fact about Rust",
                importance=0.9,
                accuracy_score=0.6,
            )
        ]
        await _run(
            ops, store=[SemanticMemory(id="mem-1", content="old fact about Python")], on_conflict=capture_callback
        )

        assert len(captured_ctx) == 1
        ctx = captured_ctx[0]
        assert ctx.old_memory_id == "mem-1"
        assert ctx.old_content == "old fact about Python"
        assert ctx.new_content == "new fact about Rust"
        assert ctx.accuracy_score == 0.6
        assert ctx.importance == 0.9
        assert ctx.merge_suggestion == "new fact about Rust"


class TestCustomThresholds:
    """Tests that ConsolidationConfig thresholds override defaults."""

    @pytest.mark.asyncio
    async def test_custom_importance_threshold(self) -> None:
        config = ConsolidationConfig(conflict_importance_threshold=0.9)
        callback = AsyncMock(return_value=ConflictResolution.PENDING)
        ops = [CorrectOp(memory_id="mem-1", corrected_content="new", importance=0.8, accuracy_score=0.5)]
        stats, _ = await _run(ops, on_conflict=callback, config=config)
        callback.assert_not_called()
        assert stats.corrected == 1

    @pytest.mark.asyncio
    async def test_custom_confidence_threshold(self) -> None:
        config = ConsolidationConfig(conflict_confidence_threshold=0.5)
        callback = AsyncMock(return_value=ConflictResolution.PENDING)
        ops = [CorrectOp(memory_id="mem-1", corrected_content="new", importance=0.8, accuracy_score=0.6)]
        stats, _ = await _run(ops, on_conflict=callback, config=config)
        callback.assert_not_called()
        assert stats.corrected == 1


class TestMergeOpUnaffectedByConflictCallback:
    """MergeOp never routes to on_conflict — only CorrectOp does."""

    @pytest.mark.asyncio
    async def test_merge_ignores_callback(self) -> None:
        callback = AsyncMock(return_value=ConflictResolution.PENDING)
        ops = [MergeOp(source_ids=["a", "b"], merged_content="merged")]
        stats, _ = await _run(ops, on_conflict=callback)
        callback.assert_not_called()
        assert stats.merged == 1
        assert stats.routed_to_user == 0


class TestLockedRuleSkipsConflict:
    """User-locked procedural rules bypass conflict routing entirely."""

    @pytest.mark.asyncio
    async def test_locked_rule_skips(self) -> None:
        callback = AsyncMock(return_value=ConflictResolution.PENDING)
        locked = ProceduralMemory(
            id="mem-1", content="locked rule", trigger="asked", action="answer", is_user_locked=True
        )
        ops = [CorrectOp(memory_id="mem-1", corrected_content="new", importance=0.9, accuracy_score=0.5)]
        stats, manager = await _run(ops, store=[locked], on_conflict=callback)
        callback.assert_not_called()
        assert stats.corrected == 0
        assert stats.routed_to_user == 0
        assert stats.rejected == 1
        manager.update_memory.assert_not_called()


class TestNonSemanticMemoryCorrection:
    """When existing is not SemanticMemory, uses update_memory instead of correct_memory."""

    @pytest.mark.asyncio
    async def test_non_semantic_uses_update(self) -> None:
        rule = ProceduralMemory(id="mem-1", content="old rule", trigger="asked", action="answer")
        ops = [CorrectOp(memory_id="mem-1", corrected_content="updated rule", importance=0.3, accuracy_score=0.95)]
        stats, manager = await _run(ops, store=[rule], on_conflict=None)
        assert stats.updated == 1
        assert stats.corrected == 0
        manager.update_memory.assert_called_once_with(
            "mem-1", importance=None, confidence=None, content="updated rule", metadata=None, allow_protected=False
        )
        manager.correct_memory.assert_not_called()


class TestCallbackExceptionHandling:
    """Callback exception is caught by the outer try/except, incrementing errors."""

    @pytest.mark.asyncio
    async def test_callback_exception_increments_errors(self) -> None:
        async def failing_callback(ctx: object) -> ConflictResolution:
            raise RuntimeError("callback crashed")

        ops = [CorrectOp(memory_id="mem-1", corrected_content="new", importance=0.9, accuracy_score=0.5)]
        stats, _ = await _run(ops, on_conflict=failing_callback)
        assert stats.errors == 1
        assert stats.corrected == 0
        assert stats.routed_to_user == 0


class TestMultipleOpsInBatch:
    """Multiple CorrectOps with mixed routing decisions."""

    @pytest.mark.asyncio
    async def test_mixed_routing(self) -> None:
        call_count = 0

        async def alternating_callback(ctx: object) -> ConflictResolution:
            nonlocal call_count
            call_count += 1
            return ConflictResolution.PENDING if call_count == 1 else ConflictResolution.KEEP_NEW

        ops = [
            CorrectOp(memory_id="mem-1", corrected_content="new1", importance=0.9, accuracy_score=0.5),
            CorrectOp(memory_id="mem-2", corrected_content="new2", importance=0.3, accuracy_score=0.5),
            CorrectOp(memory_id="mem-3", corrected_content="new3", importance=0.8, accuracy_score=0.6),
        ]
        stats, _ = await _run(ops, on_conflict=alternating_callback)
        assert stats.routed_to_user == 1
        assert stats.corrected == 2
        assert call_count == 2


class TestBoundaryThresholds:
    """Exact boundary values for importance and accuracy thresholds."""

    @pytest.mark.asyncio
    async def test_exact_importance_threshold_triggers(self) -> None:
        """importance == 0.6 (exactly at threshold) should trigger routing."""
        callback = AsyncMock(return_value=ConflictResolution.PENDING)
        ops = [CorrectOp(memory_id="mem-1", corrected_content="new", importance=0.6, accuracy_score=0.5)]
        stats, _ = await _run(ops, on_conflict=callback)
        callback.assert_called_once()
        assert stats.routed_to_user == 1

    @pytest.mark.asyncio
    async def test_exact_accuracy_threshold_skips(self) -> None:
        """accuracy == 0.85 (exactly at threshold) should NOT trigger routing."""
        callback = AsyncMock(return_value=ConflictResolution.PENDING)
        ops = [CorrectOp(memory_id="mem-1", corrected_content="new", importance=0.9, accuracy_score=0.85)]
        stats, _ = await _run(ops, on_conflict=callback)
        callback.assert_not_called()
        assert stats.corrected == 1

    @pytest.mark.asyncio
    async def test_just_below_accuracy_triggers(self) -> None:
        """accuracy == 0.84 (just below threshold) should trigger routing."""
        callback = AsyncMock(return_value=ConflictResolution.PENDING)
        ops = [CorrectOp(memory_id="mem-1", corrected_content="new", importance=0.9, accuracy_score=0.84)]
        stats, _ = await _run(ops, on_conflict=callback)
        callback.assert_called_once()
        assert stats.routed_to_user == 1

    @pytest.mark.asyncio
    async def test_just_below_importance_skips(self) -> None:
        """importance == 0.59 (just below threshold) should skip routing."""
        callback = AsyncMock(return_value=ConflictResolution.PENDING)
        ops = [CorrectOp(memory_id="mem-1", corrected_content="new", importance=0.59, accuracy_score=0.5)]
        stats, _ = await _run(ops, on_conflict=callback)
        callback.assert_not_called()
        assert stats.corrected == 1
