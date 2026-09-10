"""Architecture guard: idea-to-build-staged-artifact skill must preserve its core operating contract.

[INPUT]
- assets/prebuilt_skills/idea-to-build-staged-artifact/SKILL.md

[OUTPUT]
- Architecture tests ensuring idea-to-build-staged-artifact skill retains 5-stage artifact pipeline, product-implementation separation, spec review gate, and agent handoff contracts

[POS]
Architecture test verifying the operational integrity and contract stability of the idea-to-build-staged-artifact prebuilt skill.
"""

from __future__ import annotations

from pathlib import Path

import pytest

_CANDIDATES = (
    Path(__file__).resolve().parents[2] / "assets" / "prebuilt_skills" / "idea-to-build-staged-artifact" / "SKILL.md",
    Path(__file__).resolve().parents[4] / "assets" / "prebuilt_skills" / "idea-to-build-staged-artifact" / "SKILL.md",
)
_SKILL_MD = next((p for p in _CANDIDATES if p.is_file()), _CANDIDATES[0])

_CORE_STAGE_MARKERS = (
    "01_product_intent.md",
    "02_system_architecture.md",
    "03_build_handoff.md",
)

_CONTRACT_MARKERS = (
    # Modes of operation
    "Lite Mode (Quick-Capture)",
    "Full Mode (Comprehensive Architecture)",
    # Spec review gate
    "Spec Review Gate",
    # Out of scope discipline
    "OUT-OF-SCOPE",
    # Single-file handoff
    "single-file",
    # Tool declarations in frontmatter
    "file_write_tool",
    "file_read_tool",
    "file_edit_tool",
)

_MAX_SKILL_CHARS = 12_000


@pytest.fixture(scope="module")
def skill_text() -> str:
    if not _SKILL_MD.is_file():
        pytest.fail(f"Missing idea-to-build-staged-artifact skill: {_SKILL_MD}")
    return _SKILL_MD.read_text(encoding="utf-8")


def test_idea_to_build_file_exists() -> None:
    assert _SKILL_MD.is_file(), f"File does not exist: {_SKILL_MD}"


def test_idea_to_build_char_limit(skill_text: str) -> None:
    assert len(skill_text) <= _MAX_SKILL_CHARS, (
        f"idea-to-build-staged-artifact SKILL.md is {len(skill_text)} chars, exceeding {_MAX_SKILL_CHARS}"
    )


def test_idea_to_build_contains_all_stages(skill_text: str) -> None:
    missing = [m for m in _CORE_STAGE_MARKERS if m not in skill_text]
    assert not missing, f"idea-to-build-staged-artifact SKILL.md is missing stages: {missing}"


def test_idea_to_build_contains_contract_markers(skill_text: str) -> None:
    missing = [m for m in _CONTRACT_MARKERS if m not in skill_text]
    assert not missing, f"idea-to-build-staged-artifact SKILL.md is missing contract markers: {missing}"
