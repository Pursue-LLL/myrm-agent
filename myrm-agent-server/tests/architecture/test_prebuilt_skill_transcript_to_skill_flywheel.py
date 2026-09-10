"""Architecture guard: transcript-to-skill-flywheel skill must preserve its core operating contract.

[INPUT]
- assets/prebuilt_skills/transcript-to-skill-flywheel/SKILL.md

[OUTPUT]
- Architecture tests ensuring transcript-to-skill-flywheel retains 4-phase flywheel pipeline, parameterization rules, and cron linking contract

[POS]
Architecture test verifying the operational integrity and contract stability of the transcript-to-skill-flywheel prebuilt skill.
"""

from __future__ import annotations

from pathlib import Path

import pytest

_SKILL_MD = (
    Path(__file__).resolve().parents[3]
    / "assets"
    / "prebuilt_skills"
    / "transcript-to-skill-flywheel"
    / "SKILL.md"
)

_CORE_PHASES = (
    "Transcript Analysis & Milestone Distillation",
    "Variable Parameterization & Boundary Isolation",
    "Standardized SKILL.md Packaging",
    "Cron Job Automation Linking",
)

_CONTRACT_MARKERS = (
    "Transcript-to-Skill Flywheel",
    "Variable Parameterization",
    "cron_expression",
    "skill_ids",
)

_MAX_SKILL_CHARS = 12_000


@pytest.fixture(scope="module")
def skill_text() -> str:
    if not _SKILL_MD.is_file():
        pytest.fail(f"Missing transcript-to-skill-flywheel skill: {_SKILL_MD}")
    return _SKILL_MD.read_text(encoding="utf-8")


def test_transcript_to_skill_flywheel_file_exists() -> None:
    assert _SKILL_MD.is_file(), f"File does not exist: {_SKILL_MD}"


def test_transcript_to_skill_flywheel_char_limit(skill_text: str) -> None:
    assert len(skill_text) <= _MAX_SKILL_CHARS, (
        f"transcript-to-skill-flywheel SKILL.md is {len(skill_text)} chars, exceeding {_MAX_SKILL_CHARS}"
    )


def test_transcript_to_skill_flywheel_contains_all_phases(skill_text: str) -> None:
    missing = [phase for phase in _CORE_PHASES if phase not in skill_text]
    assert not missing, f"transcript-to-skill-flywheel SKILL.md is missing phases: {missing}"


def test_transcript_to_skill_flywheel_contains_contract_markers(skill_text: str) -> None:
    missing = [marker for marker in _CONTRACT_MARKERS if marker not in skill_text]
    assert not missing, f"transcript-to-skill-flywheel SKILL.md is missing contract markers: {missing}"
