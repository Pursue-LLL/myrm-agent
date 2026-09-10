"""Architecture guard: wiki-skill-three-tier skill must preserve its core operating contract.

[INPUT]
- assets/prebuilt_skills/wiki-skill-three-tier/SKILL.md

[OUTPUT]
- Architecture tests ensuring wiki-skill-three-tier skill retains 3-tier architecture, asymmetric evolution invariant, and wiki toolchain integration.

[POS]
Architecture test verifying the operational integrity and contract stability of the wiki-skill-three-tier prebuilt skill.
"""

from __future__ import annotations

from pathlib import Path
import pytest

_SKILL_MD = (
    Path(__file__).resolve().parents[3]
    / "assets"
    / "prebuilt_skills"
    / "wiki-skill-three-tier"
    / "SKILL.md"
)

_TIER_MARKERS = (
    "Tier 1: Traces",
    "Tier 2: Wiki",
    "Tier 3: Skills",
)

_INVARIANT_MARKERS = (
    "Asymmetric Evolution Invariant",
    "The 4-Phase Compilation Cycle",
    "Standard Execution SOP",
)

_TOOL_MARKERS = (
    "wiki_ingest",
    "wiki_query",
    "wiki_apply",
)

_MAX_SKILL_CHARS = 12_000


@pytest.fixture(scope="module")
def skill_text() -> str:
    if not _SKILL_MD.is_file():
        pytest.fail(f"Missing wiki-skill-three-tier skill: {_SKILL_MD}")
    return _SKILL_MD.read_text(encoding="utf-8")


def test_wiki_skill_three_tier_file_exists() -> None:
    assert _SKILL_MD.is_file(), f"File does not exist: {_SKILL_MD}"


def test_wiki_skill_three_tier_char_limit(skill_text: str) -> None:
    assert len(skill_text) <= _MAX_SKILL_CHARS, (
        f"wiki-skill-three-tier SKILL.md is {len(skill_text)} chars, exceeding {_MAX_SKILL_CHARS}"
    )


def test_wiki_skill_three_tier_contains_tiers(skill_text: str) -> None:
    missing = [t for t in _TIER_MARKERS if t not in skill_text]
    assert not missing, f"wiki-skill-three-tier SKILL.md is missing tier markers: {missing}"


def test_wiki_skill_three_tier_contains_invariants(skill_text: str) -> None:
    missing = [i for i in _INVARIANT_MARKERS if i not in skill_text]
    assert not missing, f"wiki-skill-three-tier SKILL.md is missing invariant markers: {missing}"


def test_wiki_skill_three_tier_contains_wiki_tools(skill_text: str) -> None:
    missing = [tool for tool in _TOOL_MARKERS if tool not in skill_text]
    assert not missing, f"wiki-skill-three-tier SKILL.md is missing wiki tool markers: {missing}"
