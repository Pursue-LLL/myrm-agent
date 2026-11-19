"""Tests for migration lane preview helpers."""

from __future__ import annotations

from app.services.migration.source.source_migration_types import (
    INSTRUCTION_CHAR_WARN_THRESHOLD,
    MigrationLanePreview,
    SourceInstructionPlan,
    build_lane_previews,
    instruction_char_total,
)


def _credential_lane(*, has_api_keys: bool, secrets_importable: bool, providers_ready: bool) -> MigrationLanePreview:
    lanes = build_lane_previews(
        instruction=SourceInstructionPlan(competitor="hermes", agent_persona="hi"),
        memory_mapped=1,
        memory_status="ready",
        skill_count=0,
        has_api_keys=has_api_keys,
        secrets_importable=secrets_importable,
        providers_ready=providers_ready,
        include_episodic=False,
    )
    return next(item for item in lanes if item.lane == "credential")


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
        secrets_importable=True,
        providers_ready=True,
        include_episodic=False,
    )
    instruction = next(item for item in lanes if item.lane == "instruction")
    assert instruction.status == "warning"
    assert "chars total" in instruction.detail
    assert [part.code for part in instruction.detail_parts] == ["instruction_persona", "instruction_large"]
    assert instruction.detail_parts[0].params == {"chars": INSTRUCTION_CHAR_WARN_THRESHOLD + 1}


def test_build_lane_previews_marks_credentials_critical_without_providers() -> None:
    credential = _credential_lane(has_api_keys=True, secrets_importable=True, providers_ready=False)

    assert credential.status == "critical"
    assert "providers" in credential.detail.lower()
    assert [part.code for part in credential.detail_parts] == ["credential_no_providers"]


def test_keys_the_import_can_read_are_offered_as_an_opt_in_import() -> None:
    credential = _credential_lane(has_api_keys=True, secrets_importable=True, providers_ready=True)

    assert credential.status == "manual"
    assert [part.code for part in credential.detail_parts] == ["credential_opt_in"]


def test_keys_the_import_cannot_read_are_left_to_manual_entry() -> None:
    credential = _credential_lane(has_api_keys=True, secrets_importable=False, providers_ready=True)

    assert credential.status == "manual"
    assert "import" not in credential.detail.lower()
    assert [part.code for part in credential.detail_parts] == ["credential_manual"]


def test_a_source_without_keys_has_no_credential_work() -> None:
    credential = _credential_lane(has_api_keys=False, secrets_importable=False, providers_ready=True)

    assert credential.status == "missing"
    assert [part.code for part in credential.detail_parts] == ["credential_none"]
