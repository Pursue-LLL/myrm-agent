"""Architecture guard: sesa-veriskill-evolution skill must preserve its core operating contract.

[INPUT]
- assets/prebuilt_skills/sesa-veriskill-evolution/SKILL.md

[OUTPUT]
- Architecture tests ensuring sesa-veriskill-evolution skill retains 4-way causal attribution matrix, net-score formulas, and benchmark gating schemas.

[POS]
Architecture test verifying the operational integrity and contract stability of the sesa-veriskill-evolution prebuilt skill.
"""

from __future__ import annotations

from pathlib import Path

import pytest

_SKILL_MD = (
    Path(__file__).resolve().parents[3]
    / "assets"
    / "prebuilt_skills"
    / "sesa-veriskill-evolution"
    / "SKILL.md"
)

_ATTRIBUTION_MARKERS = (
    "Helpful",
    "Hurtful",
    "Spurious",
    "Redundant",
)

_SCHEMA_MARKERS = (
    "The 4-Way Causal Attribution Matrix",
    "Net Score",
    "Differential Case Matrix",
    "Standard Execution SOP",
)

_MAX_SKILL_CHARS = 12_000


@pytest.fixture(scope="module")
def skill_text() -> str:
    if not _SKILL_MD.is_file():
        pytest.fail(f"Missing sesa-veriskill-evolution skill: {_SKILL_MD}")
    return _SKILL_MD.read_text(encoding="utf-8")


def test_sesa_veriskill_evolution_file_exists() -> None:
    assert _SKILL_MD.is_file(), f"File does not exist: {_SKILL_MD}"


def test_sesa_veriskill_evolution_char_limit(skill_text: str) -> None:
    assert len(skill_text) <= _MAX_SKILL_CHARS, (
        f"sesa-veriskill-evolution SKILL.md is {len(skill_text)} chars, exceeding {_MAX_SKILL_CHARS}"
    )


def test_sesa_veriskill_evolution_contains_attributions(skill_text: str) -> None:
    missing = [a for a in _ATTRIBUTION_MARKERS if a not in skill_text]
    assert not missing, f"sesa-veriskill-evolution SKILL.md is missing attribution markers: {missing}"


def test_sesa_veriskill_evolution_contains_schema_markers(skill_text: str) -> None:
    missing = [s for s in _SCHEMA_MARKERS if s not in skill_text]
    assert not missing, f"sesa-veriskill-evolution SKILL.md is missing schema markers: {missing}"
