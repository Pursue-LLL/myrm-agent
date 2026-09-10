"""Architecture guard: historical-transcript-auditor skill must preserve its core operating contract.

[INPUT]
- assets/prebuilt_skills/historical-transcript-auditor/SKILL.md

[OUTPUT]
- Architecture tests ensuring historical-transcript-auditor skill retains 4-phase workflow, failure typologies, and profile refactoring contracts.
"""

from __future__ import annotations

from pathlib import Path

import pytest

_SKILL_MD = (
    Path(__file__).resolve().parents[2]
    / "assets"
    / "prebuilt_skills"
    / "historical-transcript-auditor"
    / "SKILL.md"
)

_PHASE_MARKERS = (
    "Phase 1: Multi-Session Ingestion",
    "Phase 2: Bottleneck & Failure Pattern Clustering",
    "Phase 3: SubAgent Persona & Boundary Gap Diagnosis",
    "Phase 4: Persona Refactoring Blueprint",
)

_FAILURE_TYPOLOGIES = (
    "Tool Thrashing",
    "Persona Conflict",
    "Prompt Drift",
    "Hallucinated Tooling",
)

_MAX_SKILL_CHARS = 12_000


@pytest.fixture(scope="module")
def skill_text() -> str:
    if not _SKILL_MD.is_file():
        pytest.fail(f"Missing historical-transcript-auditor skill: {_SKILL_MD}")
    return _SKILL_MD.read_text(encoding="utf-8")


def test_historical_transcript_auditor_file_exists() -> None:
    assert _SKILL_MD.is_file(), f"File does not exist: {_SKILL_MD}"


def test_historical_transcript_auditor_char_limit(skill_text: str) -> None:
    assert len(skill_text) <= _MAX_SKILL_CHARS, (
        f"historical-transcript-auditor SKILL.md is {len(skill_text)} chars, exceeding {_MAX_SKILL_CHARS}"
    )


def test_historical_transcript_auditor_contains_all_phases(skill_text: str) -> None:
    missing = [p for p in _PHASE_MARKERS if p not in skill_text]
    assert not missing, f"historical-transcript-auditor SKILL.md missing phase markers: {missing}"


def test_historical_transcript_auditor_contains_typologies(skill_text: str) -> None:
    missing = [t for t in _FAILURE_TYPOLOGIES if t not in skill_text]
    assert not missing, f"historical-transcript-auditor SKILL.md missing failure typologies: {missing}"
