"""Tests for instruction rollback metadata roundtrip."""

from __future__ import annotations

from app.services.migration.source_migration_types import InstructionApplyResult
from app.services.migration.instruction_writer import (
    instruction_rollback_record_from_apply,
    instruction_rollback_record_from_metadata,
    instruction_rollback_record_to_metadata,
)


def test_instruction_rollback_metadata_roundtrip() -> None:
    result = InstructionApplyResult(
        target_agent_id="agent-import-1",
        agent_created=True,
        global_instructions_updated=True,
        workspace_rules_written=1,
        workspace_rules_skipped=2,
        profile_snapshot_id="snap-123",
        previous_global_instructions="old global",
        written_rule_paths=("/tmp/.myrm/rules/imported-hermes-style.md",),
    )
    record = instruction_rollback_record_from_apply(result, competitor="hermes")
    raw = instruction_rollback_record_to_metadata(record)
    restored = instruction_rollback_record_from_metadata(raw)

    assert restored is not None
    assert restored.target_agent_id == "agent-import-1"
    assert restored.agent_created is True
    assert restored.profile_snapshot_id == "snap-123"
    assert restored.previous_global_instructions == "old global"
    assert len(restored.written_rule_paths) == 1
