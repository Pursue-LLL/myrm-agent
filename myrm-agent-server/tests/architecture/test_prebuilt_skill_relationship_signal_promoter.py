"""Architecture guard: relationship-signal-promoter skill must preserve its core operating contract.

[INPUT]
- assets/prebuilt_skills/relationship-signal-promoter/SKILL.md

[OUTPUT]
- Architecture tests ensuring relationship-signal-promoter skill retains signal triage,
  manual promotion gate, non-work task isolation, and kanban dispatch contracts.

[POS]
Architecture test verifying the operational integrity and contract stability of the relationship-signal-promoter prebuilt skill.
"""

from __future__ import annotations

from pathlib import Path
import pytest

_SKILL_MD = (
    Path(__file__).resolve().parents[2]
    / "assets"
    / "prebuilt_skills"
    / "relationship-signal-promoter"
    / "SKILL.md"
)

_CORE_MODULE_MARKERS = (
    "relationship-signal-promoter",
    "Manual Promotion Gate",
    "Signal Sensing & Triage",
    "Signal Card Construction",
    "Standardized Kanban Dispatch",
    "[RELATIONSHIP]",
)

_SAFETY_CONTRACT_MARKERS = (
    # Zero unconfirmed kanban writing rule
    "NEVER",
    "kanban_add_task",
    "kanban_list_tasks",
    # Four-phase SOP markers
    "Phase 1: Signal Sensing & Triage",
    "Phase 2: Signal Card Construction",
    "Phase 3: Manual Promotion Gate",
    "Phase 4: Standardized Kanban Dispatch",
)

_MAX_SKILL_CHARS = 12_000


@pytest.fixture(scope="module")
def skill_text() -> str:
    if not _SKILL_MD.is_file():
        pytest.fail(f"Missing relationship-signal-promoter skill: {_SKILL_MD}")
    return _SKILL_MD.read_text(encoding="utf-8")


def test_relationship_signal_promoter_skill_exists_and_bounded(skill_text: str) -> None:
    assert _SKILL_MD.is_file(), f"File does not exist: {_SKILL_MD}"
    assert len(skill_text) <= _MAX_SKILL_CHARS, (
        f"relationship-signal-promoter SKILL.md is {len(skill_text)} chars, exceeding {_MAX_SKILL_CHARS}"
    )


def test_relationship_signal_promoter_contains_core_markers(skill_text: str) -> None:
    missing = [m for m in _CORE_MODULE_MARKERS if m not in skill_text]
    assert not missing, f"relationship-signal-promoter SKILL.md is missing core markers: {missing}"


def test_relationship_signal_promoter_contains_safety_contract_markers(skill_text: str) -> None:
    missing = [m for m in _SAFETY_CONTRACT_MARKERS if m not in skill_text]
    assert not missing, f"relationship-signal-promoter SKILL.md is missing safety contract markers: {missing}"
