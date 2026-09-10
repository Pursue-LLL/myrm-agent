"""Architecture guard: wiki-skill-evolution skill must preserve its core operating contract.

[INPUT]
- assets/prebuilt_skills/wiki-skill-evolution/SKILL.md

[OUTPUT]
- Architecture tests ensuring wiki-skill-evolution skill retains 3-tier decoupled architecture, asymmetric durability invariant, and 4-phase compilation SOP.

[POS]
Architecture test verifying the operational integrity and contract stability of the wiki-skill-evolution prebuilt skill.
"""

from __future__ import annotations

from pathlib import Path

import pytest

_SKILL_MD = (
    Path(__file__).resolve().parents[2]
    / "assets"
    / "prebuilt_skills"
    / "wiki-skill-evolution"
    / "SKILL.md"
)

_CORE_TIER_MARKERS = (
    "Tier 1: Ephemeral Execution Traces",
    "Tier 2: Durable LLM Wiki Knowledge Concepts",
    "Tier 3: Volatile Executable Skill SOPs",
)

_CONTRACT_MARKERS = (
    "Asymmetric Durability Invariant",
    "wiki/concepts/",
    "Asymmetric Rollback Gate",
    "file_read_tool",
    "file_write_tool",
    "memory_save_tool",
)

_MAX_SKILL_CHARS = 12_000


@pytest.fixture(scope="module")
def skill_text() -> str:
    if not _SKILL_MD.is_file():
        pytest.fail(f"Missing wiki-skill-evolution skill: {_SKILL_MD}")
    return _SKILL_MD.read_text(encoding="utf-8")


def test_wiki_skill_evolution_file_exists() -> None:
    assert _SKILL_MD.is_file(), f"File does not exist: {_SKILL_MD}"


def test_wiki_skill_evolution_char_limit(skill_text: str) -> None:
    assert len(skill_text) <= _MAX_SKILL_CHARS, (
        f"wiki-skill-evolution SKILL.md is {len(skill_text)} chars, exceeding {_MAX_SKILL_CHARS}"
    )


def test_wiki_skill_evolution_contains_all_tiers(skill_text: str) -> None:
    missing = [t for t in _CORE_TIER_MARKERS if t not in skill_text]
    assert not missing, f"wiki-skill-evolution SKILL.md is missing tiers: {missing}"


def test_wiki_skill_evolution_contains_contract_markers(skill_text: str) -> None:
    missing = [m for m in _CONTRACT_MARKERS if m not in skill_text]
    assert not missing, f"wiki-skill-evolution SKILL.md is missing contract markers: {missing}"
