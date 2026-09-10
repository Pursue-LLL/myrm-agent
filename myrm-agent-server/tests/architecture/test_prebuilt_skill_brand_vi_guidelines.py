"""Architecture guard: brand-vi-guidelines skill must preserve its core operating contract.

[INPUT]
- assets/prebuilt_skills/brand-vi-guidelines/SKILL.md

[OUTPUT]
- Architecture tests ensuring brand-vi-guidelines skill retains 5 core VI pillars,
  WCAG AA contrast, 16:9 safe zone padding, anti-wall-of-text, and machine-readable tokens.

[POS]
Architecture test verifying the operational integrity and contract stability of the brand-vi-guidelines prebuilt skill.
"""

from __future__ import annotations

from pathlib import Path
import pytest

_SKILL_MD = (
    Path(__file__).resolve().parents[2]
    / "assets"
    / "prebuilt_skills"
    / "brand-vi-guidelines"
    / "SKILL.md"
)

_CORE_MODULE_MARKERS = (
    "brand-vi-guidelines",
    "5 Core VI Pillars",
    "Color Palette & Accessibility Matrix",
    "Typography Hierarchy",
    "Grid & Spacing System",
    "Component Elevation & Border Radius",
    "Anti-Patterns & Negative Rules",
)

_SAFETY_CONTRACT_MARKERS = (
    "WCAG AA",
    "16:9",
    "anti-wall-of-text",
    "brand_name",
    "tokens",
    "rules",
    "Downstream Deliverables Enforcement",
)

_MAX_SKILL_CHARS = 12_000


@pytest.fixture(scope="module")
def skill_text() -> str:
    if not _SKILL_MD.is_file():
        pytest.fail(f"Missing brand-vi-guidelines skill: {_SKILL_MD}")
    return _SKILL_MD.read_text(encoding="utf-8")


def test_brand_vi_guidelines_skill_exists_and_bounded(skill_text: str) -> None:
    assert _SKILL_MD.is_file(), f"File does not exist: {_SKILL_MD}"
    assert len(skill_text) <= _MAX_SKILL_CHARS, (
        f"brand-vi-guidelines SKILL.md exceeded {_MAX_SKILL_CHARS} characters: {len(skill_text)}"
    )


def test_brand_vi_guidelines_contains_core_markers(skill_text: str) -> None:
    for marker in _CORE_MODULE_MARKERS:
        assert marker in skill_text, f"Missing core marker '{marker}' in SKILL.md"


def test_brand_vi_guidelines_contains_safety_contract_markers(skill_text: str) -> None:
    for marker in _SAFETY_CONTRACT_MARKERS:
        assert marker in skill_text, f"Missing safety contract marker '{marker}' in SKILL.md"
