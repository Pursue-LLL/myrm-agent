"""Architecture guard: x-publish-schedule skill must preserve its core operating contract.

[INPUT]
- assets/prebuilt_skills/x-publish-schedule/SKILL.md

[OUTPUT]
- Architecture tests ensuring x-publish-schedule skill retains its 4-phase safe publishing pipeline,
  HITL confirmation gate, weighted character rules, and scheduling idempotency readback.

[POS]
Architecture test verifying the operational integrity and contract stability of the x-publish-schedule prebuilt skill.
"""

from __future__ import annotations

from pathlib import Path

import pytest

_SKILL_MD = (
    Path(__file__).resolve().parents[2]
    / "assets"
    / "prebuilt_skills"
    / "x-publish-schedule"
    / "SKILL.md"
)

_CORE_MODULE_MARKERS: tuple[str, ...] = (
    "x-publish-schedule",
    "Phase 1: Content Composition & Format Validation",
    "Phase 2: Sensitive Data & Compliance Screening",
    "Phase 3: Human-In-The-Loop Confirmation Gate",
    "Phase 4: Execution & Schedule Verification Readback",
)

_SAFETY_CONTRACT_MARKERS: tuple[str, ...] = (
    # Weighted Character Calculation & Thread Chunking
    "Weighted Character Calculation",
    "Single Tweet Ceiling",
    "Thread Auto-Segmentation SOP",
    # HITL confirmation gate & approval card
    "Pre-Publish Approval Card",
    "Absolute Safety Invariant",
    # Scheduling and Idempotency Readback
    "Scheduling Verification & Idempotency Readback",
    "idempotency_hash",
    # Verification criteria
    "hitl_explicit_approval_received",
    "character_and_media_compliance_passed",
    "schedule_future_timestamp_validated",
    "audit_receipt_generated",
)

_MAX_SKILL_CHARS: int = 12_000


@pytest.fixture(scope="module")
def skill_text() -> str:
    if not _SKILL_MD.is_file():
        pytest.fail(f"Missing x-publish-schedule skill: {_SKILL_MD}")
    return _SKILL_MD.read_text(encoding="utf-8")


def test_x_publish_schedule_skill_file_exists() -> None:
    assert _SKILL_MD.is_file(), f"x-publish-schedule SKILL.md does not exist at {_SKILL_MD}"


def test_x_publish_schedule_skill_file_size(skill_text: str) -> None:
    assert len(skill_text) > 0, "SKILL.md must not be empty"
    assert (
        len(skill_text) <= _MAX_SKILL_CHARS
    ), f"SKILL.md exceeds max size ({len(skill_text)} > {_MAX_SKILL_CHARS} chars)"


def test_x_publish_schedule_contains_all_core_modules(skill_text: str) -> None:
    missing = [m for m in _CORE_MODULE_MARKERS if m not in skill_text]
    assert not missing, f"x-publish-schedule SKILL.md is missing core modules: {missing}"


def test_x_publish_schedule_contains_safety_contract_markers(skill_text: str) -> None:
    missing = [m for m in _SAFETY_CONTRACT_MARKERS if m not in skill_text]
    assert not missing, f"x-publish-schedule SKILL.md is missing safety contract markers: {missing}"
