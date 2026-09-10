"""Architecture guard: PPT reporting outline and thesis statement quality gate contract in office-document skill.

[INPUT]
- assets/prebuilt_skills/office-document/SKILL.md

[OUTPUT]
- Architecture tests ensuring office-document skill retains PPT reporting outline quality gate,
  action headline requirement, pyramid principle check, MECE classification, and anti-wall-of-text rules.

[POS]
Architecture test verifying the operational integrity and contract stability of PPT reporting outline quality gate.
"""

from __future__ import annotations

from pathlib import Path
import pytest

_CANDIDATES = (
    Path(__file__).resolve().parents[2] / "assets" / "prebuilt_skills" / "office-document" / "SKILL.md",
    Path(__file__).resolve().parents[4] / "assets" / "prebuilt_skills" / "office-document" / "SKILL.md",
)
_SKILL_MD = next((p for p in _CANDIDATES if p.is_file()), _CANDIDATES[0])

_PPT_REPORTING_GATE_MARKERS = (
    # Quality gate title
    "Plan Mode Reporting Outline & Thesis Statement Quality Gate",
    # Core requirements
    "Thesis Headline Rule",
    "Pyramid Logic Check",
    "MECE",
    "反文字墙",
    "结论先行",
)


@pytest.fixture(scope="module")
def skill_text() -> str:
    if not _SKILL_MD.is_file():
        pytest.fail(f"Missing office-document skill: {_SKILL_MD}")
    return _SKILL_MD.read_text(encoding="utf-8")


def test_office_document_skill_file_exists() -> None:
    assert _SKILL_MD.is_file(), f"File does not exist: {_SKILL_MD}"


def test_ppt_reporting_outline_quality_gate_markers(skill_text: str) -> None:
    missing = [m for m in _PPT_REPORTING_GATE_MARKERS if m not in skill_text]
    assert not missing, f"office-document SKILL.md is missing PPT reporting quality gate markers: {missing}"
