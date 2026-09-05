"""Architecture guard: web-scraping skill must preserve its core operating contract.

Ensures that the Dual-Sentinel Loop Guard, Incremental Disk Cache Protocol,
Three-Dimensional Loading Modes (Next, Load More, Infinite Scroll),
and Dual-Engine Output & Artifact Delivery rules remain explicitly documented
and are never accidentally dropped in future updates.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_SKILL_MD = Path(__file__).resolve().parents[2] / "assets" / "prebuilt_skills" / "web-scraping" / "SKILL.md"

_CONTRACT_MARKERS = (
    # Three-dimensional loading modes
    "Three-Dimensional Loading Modes",
    "Mode A: Discrete Next Button",
    "Mode B: Load More Button",
    "Mode C: Infinite Scroll / Virtual List",
    # Dual-Sentinel Loop Guard
    "Dual-Sentinel Loop Guard (Mandatory Anti-Dead-Loop Protocol)",
    "Sentinel A (Row Fingerprint)",
    "Sentinel B (Bounded Max Page Cap)",
    "tbody > tr:first-child",
    # Incremental Disk Cache Protocol
    "Incremental Disk Cache Protocol (Context & Token Protection)",
    "Stream Each Page to Disk",
    "Concise Conversation Feedback",
    # Dual-Engine Output & Artifact Delivery
    "Dual-Engine Output & Artifact Delivery",
    "utf-8-sig",
    "System Artifact Registration",
)

_MAX_SKILL_CHARS = 12_000


@pytest.fixture(scope="module")
def skill_text() -> str:
    if not _SKILL_MD.is_file():
        pytest.fail(f"Missing web-scraping skill: {_SKILL_MD}")
    return _SKILL_MD.read_text(encoding="utf-8")


@pytest.mark.architecture
def test_frontmatter_declares_skill_name(skill_text: str) -> None:
    assert "name: web-scraping" in skill_text


@pytest.mark.architecture
def test_frontmatter_has_description(skill_text: str) -> None:
    assert "description:" in skill_text
    assert "scraping" in skill_text.split("description:")[1][:250].lower()


@pytest.mark.architecture
def test_frontmatter_declares_semver_version(skill_text: str) -> None:
    assert re.search(r"^version: \d+\.\d+\.\d+$", skill_text, re.MULTILINE), (
        "web-scraping SKILL.md must declare a semver 'version: x.y.z'"
    )


@pytest.mark.architecture
@pytest.mark.parametrize("marker", _CONTRACT_MARKERS)
def test_contract_marker_present(skill_text: str, marker: str) -> None:
    assert marker in skill_text, f"Required contract marker missing from web-scraping SKILL.md: {marker!r}"


@pytest.mark.architecture
def test_skill_size_within_budget(skill_text: str) -> None:
    assert len(skill_text) <= _MAX_SKILL_CHARS, (
        f"web-scraping SKILL.md is {len(skill_text)} chars, exceeding budget {_MAX_SKILL_CHARS}"
    )
