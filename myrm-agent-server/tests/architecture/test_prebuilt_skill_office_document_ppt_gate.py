"""Architecture guard: office-document skill must enforce Reporting PPT Outline Quality Gate.

[INPUT]
- assets/prebuilt_skills/office-document/SKILL.md

[OUTPUT]
- Architecture tests ensuring office-document skill retains the 4 Quality Gates for reporting presentations:
  Gate 1: Action-Oriented Takeaway Headlines (Thesis statement requirement, rejection of purely nominal labels)
  Gate 2: 16:9 Visual Container Layout Specification (Hero metrics, split comparison, card grids, chevron process)
  Gate 3: Quantified Metric Evidence (Baseline vs target numbers)
  Gate 4: Anti-Wall-of-Text & Clean Typography (Strict prohibition of raw native emojis)

[POS]
Architecture test verifying the operational integrity and contract stability of the PPT reporting quality gate.
"""

from __future__ import annotations

from pathlib import Path
import pytest

_SKILL_MD = (
    Path(__file__).resolve().parents[2]
    / "assets"
    / "prebuilt_skills"
    / "office-document"
    / "SKILL.md"
)

_CORE_GATE_MARKERS = (
    "Reporting PPT Outline Quality Gate",
    "Gate 1: Action-Oriented Takeaway Headlines",
    "Gate 2: 16:9 Visual Container Layout Specification",
    "Gate 3: Quantified Metric Evidence",
    "Gate 4: Anti-Wall-of-Text & Clean Typography",
)

_LAYOUT_CONTAINER_ARCHETYPES = (
    "hero_metric_cards",
    "split_comparison",
    "card_grid_3col",
    "sequential_chevron_process",
    "data_chart_with_callout",
    "tabular_matrix",
)

_QUALITY_DISCIPLINE_MARKERS = (
    "FORBIDDEN",
    "REQUIRED",
    "Never use raw native emojis",
    "Plan Mode Reporting Outline & Thesis Statement Quality Gate",
    "Thesis Headline Rule",
    "Pyramid Logic Check",
)


@pytest.fixture(scope="module")
def skill_text() -> str:
    if not _SKILL_MD.is_file():
        pytest.fail(f"Missing office-document skill: {_SKILL_MD}")
    return _SKILL_MD.read_text(encoding="utf-8")


def test_office_document_skill_exists_and_non_empty(skill_text: str) -> None:
    """Verify that office-document SKILL.md exists and has non-empty content."""
    assert len(skill_text.strip()) > 500, "office-document SKILL.md is unexpectedly short"


def test_reporting_ppt_outline_quality_gates_present(skill_text: str) -> None:
    """Ensure all 4 core quality gates are explicitly specified in office-document SKILL.md."""
    missing_gates = [marker for marker in _CORE_GATE_MARKERS if marker not in skill_text]
    assert not missing_gates, f"office-document SKILL.md missing PPT quality gates: {missing_gates}"


def test_layout_container_archetypes_present(skill_text: str) -> None:
    """Ensure all 16:9 visual layout container archetypes are documented."""
    missing_archetypes = [arch for arch in _LAYOUT_CONTAINER_ARCHETYPES if arch not in skill_text]
    assert not missing_archetypes, f"office-document SKILL.md missing layout archetypes: {missing_archetypes}"


def test_quality_discipline_markers_present(skill_text: str) -> None:
    """Verify prohibition of raw emojis and enforcement of thesis-driven headlines."""
    missing_disciplines = [marker for marker in _QUALITY_DISCIPLINE_MARKERS if marker not in skill_text]
    assert not missing_disciplines, f"office-document SKILL.md missing quality disciplines: {missing_disciplines}"
