"""Architecture guard: persona-voice skill must preserve its core operating contract.

[INPUT]
- assets/prebuilt_skills/persona-voice/SKILL.md

[OUTPUT]
- Architecture tests ensuring persona-voice skill retains 5-dimensional Tone of Voice matrix, sample ingestion gate, adaptive flywheel, and conversational skill preset packaging pipeline contracts

[POS]
Architecture test verifying the operational integrity and contract stability of the persona-voice prebuilt skill.
"""

from __future__ import annotations

from pathlib import Path

import pytest

_SKILL_MD = (
    Path(__file__).resolve().parents[3]
    / "assets"
    / "prebuilt_skills"
    / "persona-voice"
    / "SKILL.md"
)

_CORE_DIMENSION_MARKERS = (
    "Syntactic Pacing",
    "Lexical Palette",
    "Tonal & Rhetorical Attitude",
    "Formatting & Punctuation",
    "Negative Constraints",
)

_CONTRACT_MARKERS = (
    # Tool declarations in frontmatter
    "file_read_tool",
    "file_write_tool",
    "memory_save_tool",
    "memory_search_tool",
    # SOP & Pipeline markers
    "Extraction Mode",
    "Interactive Refinement",
    "Persistence Protocol",
    "Adaptive Flywheel",
    "Conversational Skill Preset Packaging",
    "Corpus Distillation",
    "Persona System Prompt Synthesis",
    "Few-Shot Calibration Pairs",
    "Skill Asset Manifest Export",
)

_MAX_SKILL_CHARS = 12_000


@pytest.fixture(scope="module")
def skill_text() -> str:
    if not _SKILL_MD.is_file():
        pytest.fail(f"Missing persona-voice skill: {_SKILL_MD}")
    return _SKILL_MD.read_text(encoding="utf-8")


def test_persona_voice_file_exists() -> None:
    assert _SKILL_MD.is_file(), f"File does not exist: {_SKILL_MD}"


def test_persona_voice_char_limit(skill_text: str) -> None:
    assert len(skill_text) <= _MAX_SKILL_CHARS, (
        f"persona-voice SKILL.md is {len(skill_text)} chars, exceeding {_MAX_SKILL_CHARS}"
    )


def test_persona_voice_contains_core_dimensions(skill_text: str) -> None:
    missing = [d for d in _CORE_DIMENSION_MARKERS if d not in skill_text]
    assert not missing, f"persona-voice SKILL.md is missing 5D markers: {missing}"


def test_persona_voice_contains_contract_markers(skill_text: str) -> None:
    missing = [m for m in _CONTRACT_MARKERS if m not in skill_text]
    assert not missing, f"persona-voice SKILL.md is missing contract markers: {missing}"
