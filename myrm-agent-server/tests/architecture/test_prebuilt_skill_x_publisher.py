"""Architecture guard: x-publisher skill must preserve its core operating contract.

[INPUT]
- assets/prebuilt_skills/x-publisher/SKILL.md

[OUTPUT]
- Architecture tests ensuring x-publisher skill retains character budget enforcement,
  thread splitting rules, anti-spam spacing, and mandatory HITL pre-publish signoff.

[POS]
Architecture test verifying the operational integrity and contract stability of the x-publisher prebuilt skill.
"""

from __future__ import annotations

from pathlib import Path

import pytest

_SKILL_MD = (
    Path(__file__).resolve().parents[2]
    / "assets"
    / "prebuilt_skills"
    / "x-publisher"
    / "SKILL.md"
)

_CORE_MARKERS = (
    "280",
    "Thread",
    "t.co",
    "Human-In-The-Loop",
    "ask_question_tool",
    "anti-spam",
)

_PHASE_MARKERS = (
    "Phase 1: Content Composition & Thread Segmentation",
    "Phase 2: Pre-Flight Compliance & Quality Gate",
    "Phase 3: Scheduling & Spacing",
    "Phase 4: Mandatory Human-In-The-Loop (HITL) Signoff",
)


@pytest.fixture(scope="module")
def skill_text() -> str:
    if not _SKILL_MD.is_file():
        pytest.fail(f"Missing x-publisher skill: {_SKILL_MD}")
    return _SKILL_MD.read_text(encoding="utf-8")


def test_x_publisher_skill_exists_and_bounded(skill_text: str) -> None:
    assert len(skill_text) > 1000, "Skill content too short"
    assert len(skill_text) < 15_000, "Skill content exceeds bounding budget"


def test_x_publisher_skill_has_frontmatter_and_contract(skill_text: str) -> None:
    assert skill_text.startswith("---")
    parts = skill_text.split("---")
    assert len(parts) >= 3, "Frontmatter not properly closed"
    frontmatter = parts[1]
    assert "name: x-publisher" in frontmatter
    assert "contract:" in frontmatter
    assert "verification_steps:" in frontmatter
    assert "ask_question_tool" in frontmatter


def test_x_publisher_skill_contains_all_phases(skill_text: str) -> None:
    for marker in _PHASE_MARKERS:
        assert marker in skill_text, f"Missing SOP phase marker: {marker}"


def test_x_publisher_skill_contains_core_invariants(skill_text: str) -> None:
    for marker in _CORE_MARKERS:
        assert marker in skill_text, f"Missing core invariant marker: {marker}"
