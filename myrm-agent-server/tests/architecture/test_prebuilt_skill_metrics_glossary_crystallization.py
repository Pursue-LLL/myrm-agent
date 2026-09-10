"""Architecture guard: metrics-glossary-crystallization skill must preserve its core operating contract.

[INPUT]
- assets/prebuilt_skills/metrics-glossary-crystallization/SKILL.md

[OUTPUT]
- Architecture tests ensuring metrics-glossary-crystallization retains 5-dimensional metric model, wiki tools contract, and SSOT crystallization rules

[POS]
Architecture test verifying the operational integrity and contract stability of the metrics-glossary-crystallization prebuilt skill.
"""

from __future__ import annotations

from pathlib import Path
import pytest

_SKILL_MD = (
    Path(__file__).resolve().parents[2]
    / "assets"
    / "prebuilt_skills"
    / "metrics-glossary-crystallization"
    / "SKILL.md"
)

_FIVE_DIMENSIONS = (
    "Standard Identifier & Aliases",
    "Business Definition & Objectives",
    "Formal Computation Logic & SQL",
    "Data Lineage & Granularity",
    "Anti-Patterns & Known Pitfalls",
)

_CONTRACT_MARKERS = (
    "wiki_ingest_tool",
    "wiki_query_tool",
    "wiki_apply_tool",
    "llm_wiki",
    "5-Dimensional Metric Specification",
)

_MAX_SKILL_CHARS = 12_000


@pytest.fixture(scope="module")
def skill_text() -> str:
    if not _SKILL_MD.is_file():
        pytest.fail(f"Missing metrics-glossary-crystallization skill: {_SKILL_MD}")
    return _SKILL_MD.read_text(encoding="utf-8")


def test_metrics_glossary_crystallization_file_exists() -> None:
    assert _SKILL_MD.is_file(), f"File does not exist: {_SKILL_MD}"


def test_metrics_glossary_crystallization_char_limit(skill_text: str) -> None:
    assert len(skill_text) <= _MAX_SKILL_CHARS, (
        f"metrics-glossary-crystallization SKILL.md is {len(skill_text)} chars, exceeding {_MAX_SKILL_CHARS}"
    )


def test_metrics_glossary_crystallization_contains_all_dimensions(skill_text: str) -> None:
    missing = [dim for dim in _FIVE_DIMENSIONS if dim not in skill_text]
    assert not missing, f"metrics-glossary-crystallization SKILL.md is missing dimensions: {missing}"


def test_metrics_glossary_crystallization_contains_contract_markers(skill_text: str) -> None:
    missing = [marker for marker in _CONTRACT_MARKERS if marker not in skill_text]
    assert not missing, f"metrics-glossary-crystallization SKILL.md is missing contract markers: {missing}"
