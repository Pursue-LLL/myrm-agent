"""Architecture guard: transcript-workflow-auditor skill must preserve its core operating contract.

[INPUT]
- assets/prebuilt_skills/transcript-workflow-auditor/SKILL.md

[OUTPUT]
- Architecture tests ensuring transcript-workflow-auditor skill retains 4-stage audit pipeline,
  3 cardinal execution pathologies, output contract, and operational safeguards.

[POS]
Architecture test verifying the operational integrity and contract stability of the transcript-workflow-auditor prebuilt skill.
"""

from __future__ import annotations

from pathlib import Path

import pytest

_SKILL_MD = (
    Path(__file__).resolve().parents[2]
    / "assets"
    / "prebuilt_skills"
    / "transcript-workflow-auditor"
    / "SKILL.md"
)

_CORE_MODULE_MARKERS = (
    "transcript-workflow-auditor",
    "3 cardinal execution pathologies",
    "Endless Retry Loops",
    "Tool Rejections & Permission Failures",
    "Persona Drift & Wall-of-Text Bloat",
    "4-Stage Audit & Refactoring Pipeline",
    "Trace Harvesting & Bottleneck Clustering",
    "Three-Malady Pathological Diagnosis",
    "Sub-Agent Persona System Prompt Hardening",
    "Regression Test & Verification Gate",
)

_SAFETY_CONTRACT_MARKERS = (
    "docs/audits/transcript-audit-report.md",
    "Zero Privacy Leakage",
    "Evidence-First",
)

_MAX_SKILL_CHARS = 12_000


@pytest.fixture(scope="module")
def skill_text() -> str:
    if not _SKILL_MD.is_file():
        pytest.fail(f"Missing transcript-workflow-auditor skill: {_SKILL_MD}")
    return _SKILL_MD.read_text(encoding="utf-8")


def test_transcript_workflow_auditor_skill_exists_and_bounded(skill_text: str) -> None:
    assert _SKILL_MD.is_file(), f"File does not exist: {_SKILL_MD}"
    assert len(skill_text) <= _MAX_SKILL_CHARS, (
        f"transcript-workflow-auditor SKILL.md exceeded {_MAX_SKILL_CHARS} characters: {len(skill_text)}"
    )


def test_transcript_workflow_auditor_contains_core_modules(skill_text: str) -> None:
    for marker in _CORE_MODULE_MARKERS:
        assert marker in skill_text, f"Missing core module marker: {marker}"


def test_transcript_workflow_auditor_contains_safety_contract(skill_text: str) -> None:
    for marker in _SAFETY_CONTRACT_MARKERS:
        assert marker in skill_text, f"Missing safety contract marker: {marker}"
