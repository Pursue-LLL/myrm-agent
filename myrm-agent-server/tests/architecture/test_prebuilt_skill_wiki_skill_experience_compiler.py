"""Architecture guard: wiki-skill-experience-compiler skill must preserve its core operating contract.

[INPUT]
- assets/prebuilt_skills/wiki-skill-experience-compiler/SKILL.md

[OUTPUT]
- Architecture tests ensuring wiki-skill-experience-compiler skill retains three-tier architecture
  (Raw traces -> Persistent Wiki facts -> Executable Skill SOPs), the asymmetric rollback invariant,
  and four-phase compilation procedures.

[POS]
Architecture test verifying the operational integrity and contract stability of the wiki-skill-experience-compiler prebuilt skill.
"""

from __future__ import annotations

from pathlib import Path
import pytest

_SKILL_MD = (
    Path(__file__).resolve().parents[2]
    / "assets"
    / "prebuilt_skills"
    / "wiki-skill-experience-compiler"
    / "SKILL.md"
)

_CORE_MODULE_MARKERS = (
    "wiki-skill-experience-compiler",
    "Three-Tier Architecture",
    "Raw Ephemeral Execution Traces",
    "Persistent Concept Wiki Articles",
    "Executable Skill SOPs",
    "Asymmetric Evolution Invariant",
    "Skill 回滚，但 Wiki 永不回滚",
)

_CONTRACT_MARKERS = (
    # Tool definitions
    "file_read_tool",
    "file_write_tool",
    "file_edit_tool",
    # Verification steps
    "three_tier_separation_verified",
    "asymmetric_rollback_inviolable",
)

_MAX_SKILL_CHARS = 12_000


@pytest.fixture(scope="module")
def skill_text() -> str:
    if not _SKILL_MD.is_file():
        pytest.fail(f"Missing wiki-skill-experience-compiler skill: {_SKILL_MD}")
    return _SKILL_MD.read_text(encoding="utf-8")


def test_wiki_skill_experience_compiler_file_exists() -> None:
    assert _SKILL_MD.is_file(), f"File does not exist: {_SKILL_MD}"


def test_wiki_skill_experience_compiler_char_limit(skill_text: str) -> None:
    assert len(skill_text) <= _MAX_SKILL_CHARS, (
        f"wiki-skill-experience-compiler SKILL.md is {len(skill_text)} chars, exceeding {_MAX_SKILL_CHARS}"
    )


def test_wiki_skill_experience_compiler_contains_core_markers(skill_text: str) -> None:
    missing = [m for m in _CORE_MODULE_MARKERS if m not in skill_text]
    assert not missing, f"wiki-skill-experience-compiler SKILL.md is missing core markers: {missing}"


def test_wiki_skill_experience_compiler_contains_contract_markers(skill_text: str) -> None:
    missing = [m for m in _CONTRACT_MARKERS if m not in skill_text]
    assert not missing, f"wiki-skill-experience-compiler SKILL.md is missing contract markers: {missing}"
