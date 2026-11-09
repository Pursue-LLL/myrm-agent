"""Tests for the data types of consolidation conflict routing.

Covers:
- ConflictResolution enum values
- PendingRecord conflict fields (is_conflict, conflict_old_memory_id, etc.)
- ConflictContext dataclass fields
- ConsolidationStats.routed_to_user and guard_patched counters
- Default conflict thresholds of ConsolidationConfig
"""

from __future__ import annotations

from dataclasses import fields as dc_fields
from datetime import UTC, datetime

import pytest

from myrm_agent_harness.toolkits.memory.strategies.consolidation import ConflictContext, ConsolidationStats
from myrm_agent_harness.toolkits.memory.types import ConflictResolution, MemoryType, PendingRecord


class TestConflictResolutionEnum:
    """Validates ConflictResolution enum values."""

    def test_all_values(self) -> None:
        assert set(ConflictResolution) == {
            ConflictResolution.KEEP_OLD,
            ConflictResolution.KEEP_NEW,
            ConflictResolution.MERGE,
            ConflictResolution.DISCARD_BOTH,
            ConflictResolution.PENDING,
        }

    def test_string_values(self) -> None:
        assert ConflictResolution.KEEP_OLD == "keep_old"
        assert ConflictResolution.KEEP_NEW == "keep_new"
        assert ConflictResolution.MERGE == "merge"
        assert ConflictResolution.DISCARD_BOTH == "discard_both"
        assert ConflictResolution.PENDING == "pending"

    def test_from_string(self) -> None:
        assert ConflictResolution("keep_old") == ConflictResolution.KEEP_OLD
        assert ConflictResolution("pending") == ConflictResolution.PENDING


class TestPendingRecordConflictFields:
    """Validates PendingRecord conflict-related fields."""

    def test_default_no_conflict(self) -> None:
        record = PendingRecord(memory_type=MemoryType.SEMANTIC, content="test")
        assert record.is_conflict is False
        assert record.conflict_old_memory_id is None
        assert record.conflict_old_content is None
        assert record.conflict_accuracy_score is None
        assert record.conflict_importance is None
        assert record.conflict_auto_resolve_at is None

    def test_conflict_fields_populated(self) -> None:
        auto_resolve = datetime.now(UTC)
        record = PendingRecord(
            memory_type=MemoryType.SEMANTIC,
            content="new content",
            is_conflict=True,
            conflict_old_memory_id="old-mem-1",
            conflict_old_content="old content",
            conflict_accuracy_score=0.7,
            conflict_importance=0.8,
            conflict_auto_resolve_at=auto_resolve,
        )
        assert record.is_conflict is True
        assert record.conflict_old_memory_id == "old-mem-1"
        assert record.conflict_old_content == "old content"
        assert record.conflict_accuracy_score == 0.7
        assert record.conflict_importance == 0.8
        assert record.conflict_auto_resolve_at == auto_resolve

    def test_status_resolved(self) -> None:
        record = PendingRecord(
            memory_type=MemoryType.SEMANTIC,
            content="test",
            status="resolved",
        )
        assert record.status == "resolved"

    def test_serialization_round_trip(self) -> None:
        record = PendingRecord(
            memory_type=MemoryType.SEMANTIC,
            content="conflict content",
            is_conflict=True,
            conflict_old_memory_id="old-1",
            conflict_accuracy_score=0.65,
        )
        data = record.model_dump()
        restored = PendingRecord.model_validate(data)
        assert restored.is_conflict is True
        assert restored.conflict_old_memory_id == "old-1"
        assert restored.conflict_accuracy_score == 0.65


class TestConflictContext:
    """Validates ConflictContext frozen dataclass structure."""

    def test_all_fields_present(self) -> None:
        ctx = ConflictContext(
            old_memory_id="old-1",
            old_content="Python is best",
            new_content="Rust is better",
            accuracy_score=0.7,
            importance=0.8,
            merge_suggestion="Python and Rust both have merits",
            memory_type=MemoryType.SEMANTIC,
        )
        assert ctx.old_memory_id == "old-1"
        assert ctx.old_content == "Python is best"
        assert ctx.new_content == "Rust is better"
        assert ctx.accuracy_score == 0.7
        assert ctx.importance == 0.8
        assert ctx.merge_suggestion == "Python and Rust both have merits"
        assert ctx.memory_type == MemoryType.SEMANTIC

    def test_frozen(self) -> None:
        ctx = ConflictContext(
            old_memory_id="id",
            old_content="a",
            new_content="b",
            accuracy_score=0.5,
            importance=0.5,
            merge_suggestion="c",
            memory_type=MemoryType.EPISODIC,
        )
        with pytest.raises(AttributeError):
            ctx.old_memory_id = "changed"  # type: ignore[misc]

    def test_slot_count(self) -> None:
        expected_fields = {
            "old_memory_id",
            "old_content",
            "new_content",
            "accuracy_score",
            "importance",
            "merge_suggestion",
            "memory_type",
        }
        actual_fields = {f.name for f in dc_fields(ConflictContext)}
        assert actual_fields == expected_fields


class TestConsolidationStatsRoutedField:
    """Validates routed_to_user counter on ConsolidationStats."""

    def test_default_zero(self) -> None:
        stats = ConsolidationStats()
        assert stats.routed_to_user == 0

    def test_custom_value(self) -> None:
        stats = ConsolidationStats(routed_to_user=3)
        assert stats.routed_to_user == 3


class TestConsolidationStatsGuardPatchedField:
    """Validates guard_patched counter on ConsolidationStats."""

    def test_default_zero(self) -> None:
        stats = ConsolidationStats()
        assert stats.guard_patched == 0

    def test_custom_value(self) -> None:
        stats = ConsolidationStats(guard_patched=5)
        assert stats.guard_patched == 5


class TestConsolidationConfigFields:
    """Tests ConsolidationConfig conflict-related fields."""

    def test_default_thresholds(self) -> None:
        from myrm_agent_harness.toolkits.memory.config import ConsolidationConfig

        cfg = ConsolidationConfig()
        assert cfg.conflict_importance_threshold == 0.6
        assert cfg.conflict_confidence_threshold == 0.85
