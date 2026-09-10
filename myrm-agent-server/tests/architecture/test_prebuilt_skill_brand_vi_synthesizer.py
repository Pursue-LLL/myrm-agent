"""Architecture guard: brand-vi-synthesizer skill must preserve its core operating contract.

[INPUT]
- assets/prebuilt_skills/brand-vi-synthesizer/SKILL.md

[OUTPUT]
- Architecture tests ensuring brand-vi-synthesizer skill retains 5 core pillars, WCAG AA compliance, and machine-readable token export contracts

[POS]
Architecture test verifying the operational integrity and contract stability of the brand-vi-synthesizer prebuilt skill.
"""

from __future__ import annotations

from pathlib import Path
import pytest

_SKILL_MD = (
    Path(__file__).resolve().parents[2]
    / "assets"
    / "prebuilt_skills"
    / "brand-vi-synthesizer"
    / "SKILL.md"
)

_CORE_PILLARS = (
    "Pillar 1: Color Palette",
    "Pillar 2: Typography",
    "Pillar 3: Spacing, Grid, Radius",
    "Pillar 4: Brand Voice & Written Tone",
    "Pillar 5: Brand Don'ts",
)

_CONTRACT_MARKERS = (
    "WCAG 2.1 AA",
    "tokens.css",
    "tailwind.brand.js",
    "tokens.json",
    "file_write_tool",
    "file_read_tool",
    ":root",
    ".dark",
)

_MAX_SKILL_CHARS = 16_000


@pytest.fixture(scope="module")
def skill_text() -> str:
    if not _SKILL_MD.is_file():
        pytest.fail(f"Missing brand-vi-synthesizer skill: {_SKILL_MD}")
    return _SKILL_MD.read_text(encoding="utf-8")


def test_brand_vi_synthesizer_file_exists() -> None:
    assert _SKILL_MD.is_file(), f"File does not exist: {_SKILL_MD}"


def test_brand_vi_synthesizer_char_limit(skill_text: str) -> None:
    assert len(skill_text) <= _MAX_SKILL_CHARS, (
        f"brand-vi-synthesizer SKILL.md is {len(skill_text)} chars, exceeding {_MAX_SKILL_CHARS}"
    )


def test_brand_vi_synthesizer_contains_all_pillars(skill_text: str) -> None:
    missing = [p for p in _CORE_PILLARS if p not in skill_text]
    assert not missing, f"brand-vi-synthesizer SKILL.md is missing pillars: {missing}"


def test_brand_vi_synthesizer_contains_contract_markers(skill_text: str) -> None:
    missing = [m for m in _CONTRACT_MARKERS if m not in skill_text]
    assert not missing, f"brand-vi-synthesizer SKILL.md is missing contract markers: {missing}"
