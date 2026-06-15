"""Tests for migration lane preview helpers."""

from __future__ import annotations

from app.services.migration.source_migration_types import (
    INSTRUCTION_CHAR_WARN_THRESHOLD,
    SourceInstructionPlan,
    build_lane_previews,
    instruction_char_total,
)


def test_instruction_char_total_sums_persona_rules_and_global() -> None:
    plan = SourceInstructionPlan(
        competitor="hermes",
        agent_persona="x" * 100,
        global_supplement="y" * 50,
        workspace_rules=[],
    )
    assert instruction_char_total(plan) == 150


def test_build_lane_previews_marks_large_instruction_as_warning() -> None:
    plan = SourceInstructionPlan(
        competitor="openclaw",
        agent_persona="z" * (INSTRUCTION_CHAR_WARN_THRESHOLD + 1),
    )
    lanes = build_lane_previews(
        instruction=plan,
        memory_mapped=3,
        memory_status="ready",
        skill_count=1,
        has_api_keys=True,
        providers_ready=True,
        include_episodic=False,
    )
    instruction = next(item for item in lanes if item.lane == "instruction")
    assert instruction.status == "warning"
    assert "chars total" in instruction.detail


def test_build_lane_previews_marks_credentials_critical_without_providers() -> None:
    plan = SourceInstructionPlan(competitor="hermes", agent_persona="hi")
    lanes = build_lane_previews(
        instruction=plan,
        memory_mapped=1,
        memory_status="ready",
        skill_count=0,
        has_api_keys=True,
        providers_ready=False,
        include_episodic=False,
    )
    credential = next(item for item in lanes if item.lane == "credential")
    assert credential.status == "critical"
    assert "providers" in credential.detail.lower()
