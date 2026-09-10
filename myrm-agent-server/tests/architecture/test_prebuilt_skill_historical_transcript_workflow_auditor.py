"""Architecture guard: historical-transcript-workflow-auditor skill must preserve its core operating contract.

[INPUT]
- assets/prebuilt_skills/historical-transcript-workflow-auditor/SKILL.md

[OUTPUT]
- Architecture tests ensuring historical-transcript-workflow-auditor skill retains 4-phase audit pipeline, 5 universal anti-patterns, persona refactoring prompt architecture, and deliverable report contracts

[POS]
Architecture test verifying the operational integrity and contract stability of the historical-transcript-workflow-auditor prebuilt skill.
"""

from __future__ import annotations

from pathlib import Path
import pytest

_SKILL_MD = (
    Path(__file__).resolve().parents[3]
    / "assets"
    / "prebuilt_skills"
    / "historical-transcript-workflow-auditor"
    / "SKILL.md"
)

_CORE_PHASE_MARKERS = (
    "Phase 1: Ingestion & Telemetry",
    "Phase 2: Friction & Bottleneck Clustering",
    "Phase 3: SubAgent Persona Matrix Refactoring",
    "Phase 4: Replay Benchmarking & Hardening",
)

_CONTRACT_MARKERS = (
    # Universal anti-patterns
    "Tool Parameter Hallucination",
    "Infinite Circuit-Breaker Loop",
    "Wall-of-Text",
    # 4-part persona prompt architecture
    "Domain Axioms",
    "Negative Constraints",
    "Resilient Self-Correction",
    # Subagents core directory path
    "app/config/subagents/core",
    # Deliverable report contract
    "workflow_audit_report.md",
)

_MAX_SKILL_CHARS = 12_000


@pytest.fixture(scope="module")
def skill_text() -> str:
    if not _SKILL_MD.is_file():
        pytest.fail(f"Missing historical-transcript-workflow-auditor skill: {_SKILL_MD}")
    return _SKILL_MD.read_text(encoding="utf-8")


def test_workflow_auditor_file_exists() -> None:
    assert _SKILL_MD.is_file(), f"File does not exist: {_SKILL_MD}"


def test_workflow_auditor_char_limit(skill_text: str) -> None:
    assert len(skill_text) <= _MAX_SKILL_CHARS, (
        f"historical-transcript-workflow-auditor SKILL.md is {len(skill_text)} chars, exceeding {_MAX_SKILL_CHARS}"
    )


def test_workflow_auditor_contains_all_phases(skill_text: str) -> None:
    missing = [m for m in _CORE_PHASE_MARKERS if m not in skill_text]
    assert not missing, f"historical-transcript-workflow-auditor SKILL.md is missing phases: {missing}"


def test_workflow_auditor_contains_contract_markers(skill_text: str) -> None:
    missing = [m for m in _CONTRACT_MARKERS if m not in skill_text]
    assert not missing, f"historical-transcript-workflow-auditor SKILL.md is missing contract markers: {missing}"
