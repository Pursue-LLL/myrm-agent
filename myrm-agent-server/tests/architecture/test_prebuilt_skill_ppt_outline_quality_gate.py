"""Architecture guard: ppt-outline-quality-gate skill must preserve its core operating contract.

[INPUT]
- assets/prebuilt_skills/ppt-outline-quality-gate/SKILL.md

[OUTPUT]
- Architecture tests ensuring ppt-outline-quality-gate skill retains SCQA narrative arc,
  Thesis Headline rule (action titles), anti-wall-of-text density limits, native visual container mapping,
  and quality gate audit checklist.

[POS]
Architecture test verifying the operational integrity and contract stability of the ppt-outline-quality-gate prebuilt skill.
"""

from __future__ import annotations

from pathlib import Path
import pytest

_SKILL_MD = (
    Path(__file__).resolve().parents[2]
    / "assets"
    / "prebuilt_skills"
    / "ppt-outline-quality-gate"
    / "SKILL.md"
)

_CORE_MODULE_MARKERS = (
    "ppt-outline-quality-gate",
    "Thesis Headline Rule",
    "Anti-Wall-of-Text",
    "Mandatory Native Object Mapping",
    "SCQA Narrative Arc",
)

_SAFETY_CONTRACT_MARKERS = (
    # Prohibition against empty noun-phrase headlines
    "Zero Passive Topic Labels",
    "Action-Oriented Conclusion",
    # Anti-wall-of-text density rule
    "The 6×6 Rule",
    # Native visual containers
    "visual container",
    "XL_CHART_TYPE",
    # Quality Gate Checklist
    "Quality Gate Checklist",
    # Four-phase SOP markers
    "Phase 1: SCQA Narrative & Objective Structuring",
    "Phase 2: Slide-by-Slide Thesis Formulation",
    "Phase 3: Visual & Data Object Mapping",
    "Phase 4: Gate Audit & Scoring",
)

_MAX_SKILL_CHARS = 12_000


@pytest.fixture(scope="module")
def skill_text() -> str:
    if not _SKILL_MD.is_file():
        pytest.fail(f"Missing ppt-outline-quality-gate skill: {_SKILL_MD}")
    return _SKILL_MD.read_text(encoding="utf-8")


def test_ppt_outline_quality_gate_skill_exists_and_bounded(skill_text: str) -> None:
    assert _SKILL_MD.is_file(), f"File does not exist: {_SKILL_MD}"
    assert len(skill_text) <= _MAX_SKILL_CHARS, (
        f"ppt-outline-quality-gate SKILL.md is {len(skill_text)} chars, exceeding {_MAX_SKILL_CHARS}"
    )


def test_ppt_outline_quality_gate_contains_core_markers(skill_text: str) -> None:
    missing = [m for m in _CORE_MODULE_MARKERS if m not in skill_text]
    assert not missing, f"ppt-outline-quality-gate SKILL.md is missing core markers: {missing}"


def test_ppt_outline_quality_gate_contains_safety_contract_markers(skill_text: str) -> None:
    missing = [m for m in _SAFETY_CONTRACT_MARKERS if m not in skill_text]
    assert not missing, f"ppt-outline-quality-gate SKILL.md is missing safety contract markers: {missing}"
