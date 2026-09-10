"""Architecture guard: metrics-glossary-crystallizer skill must preserve its core operating contract.

[INPUT]
- assets/prebuilt_skills/metrics-glossary-crystallizer/SKILL.md

[OUTPUT]
- Architecture tests ensuring metrics-glossary-crystallizer skill retains metric sensing,
  formal calculation specification, exclusion rules, and LLM Wiki markdown schema.

[POS]
Architecture test verifying the operational integrity and contract stability of the metrics-glossary-crystallizer prebuilt skill.
"""

from __future__ import annotations

from pathlib import Path

import pytest

_SKILL_MD = (
    Path(__file__).resolve().parents[2]
    / "assets"
    / "prebuilt_skills"
    / "metrics-glossary-crystallizer"
    / "SKILL.md"
)

_CORE_MODULE_MARKERS = (
    "metrics-glossary-crystallizer",
    "Metric Sensing & Ambiguity Detection",
    "Formal Specification & Boundary Rigor",
    "Wiki Entry Crystallization",
    "Standard Metric Wiki Markdown Schema",
)

_SAFETY_CONTRACT_MARKERS = (
    # Formula rigor and boundary rules
    "Exact Calculation Formula",
    "Exclusion Rules",
    "Boundary & Exclusions",
    # SQL implementation requirement
    "基准 SQL 实现",
    # Four-phase SOP markers
    "Phase 1: Metric Identification & Intent Parsing",
    "Phase 2: Formal Metric Specification",
    "Phase 3: Wiki Entry Crystallization",
    "Phase 4: Upstream Alignment & Cross-Validation",
)

_MAX_SKILL_CHARS = 12_000


@pytest.fixture(scope="module")
def skill_text() -> str:
    if not _SKILL_MD.is_file():
        pytest.fail(f"Missing metrics-glossary-crystallizer skill: {_SKILL_MD}")
    return _SKILL_MD.read_text(encoding="utf-8")


def test_metrics_glossary_crystallizer_skill_exists_and_bounded(skill_text: str) -> None:
    assert _SKILL_MD.is_file(), f"File does not exist: {_SKILL_MD}"
    assert len(skill_text) <= _MAX_SKILL_CHARS, (
        f"metrics-glossary-crystallizer SKILL.md is {len(skill_text)} chars, exceeding {_MAX_SKILL_CHARS}"
    )


def test_metrics_glossary_crystallizer_contains_core_markers(skill_text: str) -> None:
    missing = [m for m in _CORE_MODULE_MARKERS if m not in skill_text]
    assert not missing, f"metrics-glossary-crystallizer SKILL.md is missing core markers: {missing}"


def test_metrics_glossary_crystallizer_contains_safety_contract_markers(skill_text: str) -> None:
    missing = [m for m in _SAFETY_CONTRACT_MARKERS if m not in skill_text]
    assert not missing, f"metrics-glossary-crystallizer SKILL.md is missing safety contract markers: {missing}"
