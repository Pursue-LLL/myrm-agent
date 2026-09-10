"""Architecture guard: task-to-skill-flywheel skill must preserve its core operating contract.

[INPUT]
- assets/prebuilt_skills/task-to-skill-flywheel/SKILL.md

[OUTPUT]
- Architecture tests ensuring task-to-skill-flywheel skill retains 4-phase flywheel pipeline, parameterization schema, and CronJob coupling protocols.

[POS]
Architecture test verifying the operational integrity and contract stability of the task-to-skill-flywheel prebuilt skill.
"""

from __future__ import annotations

from pathlib import Path
import pytest

_SKILL_MD = (
    Path(__file__).resolve().parents[2]
    / "assets"
    / "prebuilt_skills"
    / "task-to-skill-flywheel"
    / "SKILL.md"
)

_PHASE_MARKERS = (
    "Stage 1: Session Trace Ingestion",
    "Stage 2: Parametric Slot Abstraction",
    "Stage 3: Standard Skill Contract Authoring",
    "Stage 4: Workspace Registration & Flywheel Linking",
)

_SCHEMA_MARKERS = (
    "Output Contract & Template",
    ".myrm/skills/{skill_slug}/SKILL.md",
    "Stage 2: Parametric Slot Abstraction",
)

_MAX_SKILL_CHARS = 12_000


@pytest.fixture(scope="module")
def skill_text() -> str:
    if not _SKILL_MD.is_file():
        pytest.fail(f"Missing task-to-skill-flywheel skill: {_SKILL_MD}")
    return _SKILL_MD.read_text(encoding="utf-8")


def test_task_to_skill_flywheel_file_exists() -> None:
    assert _SKILL_MD.is_file(), f"File does not exist: {_SKILL_MD}"


def test_task_to_skill_flywheel_char_limit(skill_text: str) -> None:
    assert len(skill_text) <= _MAX_SKILL_CHARS, (
        f"task-to-skill-flywheel SKILL.md is {len(skill_text)} chars, exceeding {_MAX_SKILL_CHARS}"
    )


def test_task_to_skill_flywheel_contains_phase_markers(skill_text: str) -> None:
    missing = [p for p in _PHASE_MARKERS if p not in skill_text]
    assert not missing, f"task-to-skill-flywheel SKILL.md is missing phase markers: {missing}"


def test_task_to_skill_flywheel_contains_schema_markers(skill_text: str) -> None:
    missing = [s for s in _SCHEMA_MARKERS if s not in skill_text]
    assert not missing, f"task-to-skill-flywheel SKILL.md is missing schema markers: {missing}"
