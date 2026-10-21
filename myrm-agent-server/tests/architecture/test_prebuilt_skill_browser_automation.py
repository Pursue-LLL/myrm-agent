"""Architecture guard: browser-automation skill must preserve its core operating contract.

Ensures that the Three-Track Decision Tree, Write Probe Protocol, Clear & Replace,
Batching guards (steps[] prioritization), and Human Handoff (HITL) rules remain
explicitly documented and are never accidentally dropped in future updates.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_SKILL_MD = Path(__file__).resolve().parents[2] / "assets" / "prebuilt_skills" / "browser-automation" / "SKILL.md"

_CONTRACT_MARKERS = (
    # Three tracks
    "Three-Track Decision Tree",
    "Track 1: Standard DOM Semantic Track",
    "Track 2: Visual Coordinate Track",
    "Track 3: Script-First Batch Processing Track",
    # Specific protocols
    "Write Probe Protocol",
    "Clear & Replace",
    "Declarative Batching (`steps[]` - Preferred Standard)",
    "Always 100% prioritize Declarative Batching (`steps[]`)",
    "verify_goal",
    "max 8 interaction steps",
    # Sensitive gate & Human handoff
    "Sensitive Gate & Human Handoff (HITL)",
    "Mandatory Handoff Triggers",
    "browser_ask_human_tool",
    "Zero Guessing Rule",
)

_MAX_SKILL_CHARS = 12_000


@pytest.fixture(scope="module")
def skill_text() -> str:
    if not _SKILL_MD.is_file():
        pytest.fail(f"Missing browser-automation skill: {_SKILL_MD}")
    return _SKILL_MD.read_text(encoding="utf-8")


@pytest.mark.architecture
def test_frontmatter_declares_skill_name(skill_text: str) -> None:
    assert "name: browser-automation" in skill_text


@pytest.mark.architecture
def test_frontmatter_has_description(skill_text: str) -> None:
    assert "description:" in skill_text
    assert "browser automation" in skill_text.split("description:")[1][:250].lower()


@pytest.mark.architecture
def test_frontmatter_declares_semver_version(skill_text: str) -> None:
    assert re.search(r"^version: \d+\.\d+\.\d+$", skill_text, re.MULTILINE), (
        "browser-automation SKILL.md must declare a semver version in frontmatter"
    )


@pytest.mark.architecture
@pytest.mark.parametrize("marker", _CONTRACT_MARKERS)
def test_contract_marker_present(skill_text: str, marker: str) -> None:
    assert marker in skill_text, f"browser-automation skill lost contract marker: {marker!r}"


@pytest.mark.architecture
def test_skill_stays_within_prompt_budget(skill_text: str) -> None:
    assert len(skill_text) < _MAX_SKILL_CHARS, (
        f"browser-automation SKILL.md is {len(skill_text)} chars; keep it below {_MAX_SKILL_CHARS}"
    )
