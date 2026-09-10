"""Architecture guard: idea-to-build-spec skill must preserve its core operating contract.

[INPUT]
- assets/prebuilt_skills/idea-to-build-spec/SKILL.md

[OUTPUT]
- Architecture tests ensuring idea-to-build-spec skill retains staged artifact directory structure (.build-specs/), product vs implementation thinking separation, and single-file build handoff contracts

[POS]
Architecture test verifying the operational integrity and contract stability of the idea-to-build-spec prebuilt skill.
"""

from __future__ import annotations

from pathlib import Path

import pytest

_SKILL_MD = (
    Path(__file__).resolve().parents[2]
    / "assets"
    / "prebuilt_skills"
    / "idea-to-build-spec"
    / "SKILL.md"
)

_CORE_PHASES = (
    "Phase 1: Ingestion & Scope Classification",
    "Phase 2: Product Thinking vs Implementation Thinking",
    "Phase 3: Staged Artifact Directory Structure",
    "Phase 4: Spec Review Gate",
    "Phase 5: Single-File Agent Build Handoff",
)

_CONTRACT_MARKERS = (
    ".build-specs/",
    "01_problem_scope.md",
    "02_tech_spec.md",
    "03_handoff.md",
    "file_write_tool",
    "file_read_tool",
    "kanban_add_task",
    "ask_question_tool",
    "Lite Mode",
    "Full Mode",
)

_MAX_SKILL_CHARS = 16_000


@pytest.fixture(scope="module")
def skill_text() -> str:
    if not _SKILL_MD.is_file():
        pytest.fail(f"Missing idea-to-build-spec skill: {_SKILL_MD}")
    return _SKILL_MD.read_text(encoding="utf-8")


def test_idea_to_build_spec_file_exists() -> None:
    assert _SKILL_MD.is_file(), f"File does not exist: {_SKILL_MD}"


def test_idea_to_build_spec_char_limit(skill_text: str) -> None:
    assert len(skill_text) <= _MAX_SKILL_CHARS, (
        f"idea-to-build-spec skill size ({len(skill_text)} chars) exceeds budget ({_MAX_SKILL_CHARS})"
    )


@pytest.mark.parametrize("phase", _CORE_PHASES)
def test_idea_to_build_spec_retains_phases(skill_text: str, phase: str) -> None:
    assert phase in skill_text, f"Missing core phase marker: {phase}"


@pytest.mark.parametrize("marker", _CONTRACT_MARKERS)
def test_idea_to_build_spec_retains_contracts(skill_text: str, marker: str) -> None:
    assert marker in skill_text, f"Missing core contract marker: {marker}"
