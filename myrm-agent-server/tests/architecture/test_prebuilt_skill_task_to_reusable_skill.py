"""Architecture guard: task-to-reusable-skill must preserve its core operating contract.

[INPUT]
- assets/prebuilt_skills/task-to-reusable-skill/SKILL.md

[OUTPUT]
- Architecture tests ensuring task-to-reusable-skill retains 4-phase flywheel pipeline, parameter extraction rules, and cron blueprint linkage.

[POS]
Architecture test verifying the operational integrity and contract stability of the task-to-reusable-skill prebuilt skill.
"""

from __future__ import annotations

from pathlib import Path
import pytest

_SKILL_MD = (
    Path(__file__).resolve().parents[2]
    / "assets"
    / "prebuilt_skills"
    / "task-to-reusable-skill"
    / "SKILL.md"
)

_PHASE_MARKERS = (
    "Phase 1: Winning Path Extraction & Parameterization",
    "Phase 2: Toolchain & Contract Synthesis",
    "Phase 3: Standard SKILL.md Assembly",
    "Phase 4: Persistence & Cron Blueprint Linkage",
)

_SCHEMA_MARKERS = (
    "Cron Blueprint",
    "potential_traps",
    "verification_steps",
    "Quality Gate Checklist",
)

_MAX_SKILL_CHARS = 12_000


@pytest.fixture(scope="module")
def skill_text() -> str:
    if not _SKILL_MD.is_file():
        pytest.fail(f"Missing task-to-reusable-skill: {_SKILL_MD}")
    return _SKILL_MD.read_text(encoding="utf-8")


def test_task_to_reusable_skill_file_exists() -> None:
    assert _SKILL_MD.is_file(), f"File does not exist: {_SKILL_MD}"


def test_task_to_reusable_skill_char_limit(skill_text: str) -> None:
    assert len(skill_text) <= _MAX_SKILL_CHARS, (
        f"task-to-reusable-skill SKILL.md is {len(skill_text)} chars, exceeding {_MAX_SKILL_CHARS}"
    )


def test_task_to_reusable_skill_contains_all_phases(skill_text: str) -> None:
    missing = [p for p in _PHASE_MARKERS if p not in skill_text]
    assert not missing, f"task-to-reusable-skill SKILL.md missing phase markers: {missing}"


def test_task_to_reusable_skill_contains_schema_markers(skill_text: str) -> None:
    missing = [s for s in _SCHEMA_MARKERS if s not in skill_text]
    assert not missing, f"task-to-reusable-skill SKILL.md missing schema markers: {missing}"
