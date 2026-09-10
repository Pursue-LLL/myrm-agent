"""Architecture guard: conversational-skill-evolution skill must preserve its core operating contract.

[INPUT]
- assets/prebuilt_skills/conversational-skill-evolution/SKILL.md

[OUTPUT]
- Architecture tests ensuring conversational-skill-evolution skill retains 4-phase evolution pipeline, intent ingestion, patch synthesis, pre-flight safety audit, and watcher hot-reload contracts

[POS]
Architecture test verifying the operational integrity and contract stability of the conversational-skill-evolution prebuilt skill.
"""

from __future__ import annotations

from pathlib import Path
import pytest

_SKILL_MD = (
    Path(__file__).resolve().parents[3]
    / "assets"
    / "prebuilt_skills"
    / "conversational-skill-evolution"
    / "SKILL.md"
)

_CORE_PHASE_MARKERS = (
    "Phase 1: Intent Ingestion",
    "Phase 2: Patch Synthesis",
    "Phase 3: Pre-flight Audit",
    "Phase 4: In-place Hot-Reload",
)

_CONTRACT_MARKERS = (
    # Intent disambiguation
    "Disambiguation",
    # Rule classes
    "Negative Constraint",
    # Safety gates
    "Tool Boundary Gate",
    "Schema Validity Gate",
    # Hot-reload integration
    "Watcher",
    # Deliverable evolution report
    "技能自我进化已生效",
)

_MAX_SKILL_CHARS = 12_000


@pytest.fixture(scope="module")
def skill_text() -> str:
    if not _SKILL_MD.is_file():
        pytest.fail(f"Missing conversational-skill-evolution skill: {_SKILL_MD}")
    return _SKILL_MD.read_text(encoding="utf-8")


def test_conversational_skill_evolution_file_exists() -> None:
    assert _SKILL_MD.is_file(), f"File does not exist: {_SKILL_MD}"


def test_conversational_skill_evolution_char_limit(skill_text: str) -> None:
    assert len(skill_text) <= _MAX_SKILL_CHARS, (
        f"conversational-skill-evolution SKILL.md is {len(skill_text)} chars, exceeding {_MAX_SKILL_CHARS}"
    )


def test_conversational_skill_evolution_contains_all_phases(skill_text: str) -> None:
    missing = [m for m in _CORE_PHASE_MARKERS if m not in skill_text]
    assert not missing, f"conversational-skill-evolution SKILL.md is missing phases: {missing}"


def test_conversational_skill_evolution_contains_contract_markers(skill_text: str) -> None:
    missing = [m for m in _CONTRACT_MARKERS if m not in skill_text]
    assert not missing, f"conversational-skill-evolution SKILL.md is missing contract markers: {missing}"
