"""Architecture guard: reverse-sop-decompiler skill must preserve its core operating contract.

[INPUT]
- assets/prebuilt_skills/reverse-sop-decompiler/SKILL.md

[OUTPUT]
- Architecture tests ensuring reverse-sop-decompiler skill retains 4-phase decompilation pipeline, Mermaid decision tree schemas, and executable agent spec generation.

[POS]
Architecture test verifying the operational integrity and contract stability of the reverse-sop-decompiler prebuilt skill.
"""

from __future__ import annotations

from pathlib import Path
import pytest

_SKILL_MD = (
    Path(__file__).resolve().parents[2]
    / "assets"
    / "prebuilt_skills"
    / "reverse-sop-decompiler"
    / "SKILL.md"
)

_PHASE_MARKERS = (
    "Phase 1: Multi-Turn Dialogue Ingestion",
    "Phase 2: Decision Node & Branch Mining",
    "Phase 3: Formal SOP Specification & Mermaid Tree Generation",
    "Phase 4: Agent Profile YAML Export",
)

_SCHEMA_MARKERS = (
    "graph TD",
    "docs/sop/{process_slug}.md",
    "Step-by-Step Operational Matrix",
)

_MAX_SKILL_CHARS = 12_000


@pytest.fixture(scope="module")
def skill_text() -> str:
    if not _SKILL_MD.is_file():
        pytest.fail(f"Missing reverse-sop-decompiler skill: {_SKILL_MD}")
    return _SKILL_MD.read_text(encoding="utf-8")


def test_reverse_sop_decompiler_file_exists() -> None:
    assert _SKILL_MD.is_file(), f"File does not exist: {_SKILL_MD}"


def test_reverse_sop_decompiler_char_limit(skill_text: str) -> None:
    assert len(skill_text) <= _MAX_SKILL_CHARS, (
        f"reverse-sop-decompiler SKILL.md is {len(skill_text)} chars, exceeding {_MAX_SKILL_CHARS}"
    )


def test_reverse_sop_decompiler_contains_phase_markers(skill_text: str) -> None:
    missing = [p for p in _PHASE_MARKERS if p not in skill_text]
    assert not missing, f"reverse-sop-decompiler SKILL.md is missing phase markers: {missing}"


def test_reverse_sop_decompiler_contains_schema_markers(skill_text: str) -> None:
    missing = [s for s in _SCHEMA_MARKERS if s not in skill_text]
    assert not missing, f"reverse-sop-decompiler SKILL.md is missing schema markers: {missing}"
