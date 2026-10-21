"""Architecture guard: project-experience-evidence-pack skill must preserve its core operating contract.

[INPUT]
- assets/prebuilt_skills/project-experience-evidence-pack/SKILL.md

[OUTPUT]
- Architecture tests ensuring project-experience-evidence-pack skill retains the 6-phase evidence chain,
  zero boastful fluff discipline, and concrete verification proof contracts.

[POS]
Architecture test verifying the operational integrity and contract stability of the project-experience-evidence-pack prebuilt skill.
"""

from __future__ import annotations

from pathlib import Path

import pytest

_SKILL_MD = (
    Path(__file__).resolve().parents[2]
    / "assets"
    / "prebuilt_skills"
    / "project-experience-evidence-pack"
    / "SKILL.md"
)

_CORE_MODULE_MARKERS = (
    "project-experience-evidence-pack",
    "Step 1: Original Intent & Constraints",
    "Step 2: v0 Initial Design / Prototype",
    "Step 3: Execution Bottlenecks & Failure Traces",
    "Step 4: Root-Cause Analysis & Fix Justifications",
    "Step 5: Verifiable Physical Proof & Benchmark",
    "Step 6: Crystallized Experience & Invariant Lessons",
)

_SAFETY_CONTRACT_MARKERS = (
    "empty boast case studies",
    "Step 1: Original Intent & Constraints (原始诉求与核心边界)",
    "Step 2: v0 Initial Design / Prototype (v0 首稿方案与基线设计)",
    "Step 3: Execution Bottlenecks & Failure Traces (执行瓶颈与真实失败轨迹)",
    "Step 4: Root-Cause Analysis & Fix Justifications (根本原因与修正依据)",
    "Step 5: Verifiable Physical Proof & Benchmark (实测物理证据与指标验收)",
    "Step 6: Crystallized Experience & Invariant Lessons (经验沉淀与防复发不变量)",
)

_MAX_SKILL_CHARS = 12_000


@pytest.fixture(scope="module")
def skill_text() -> str:
    if not _SKILL_MD.is_file():
        pytest.fail(f"Missing project-experience-evidence-pack skill: {_SKILL_MD}")
    return _SKILL_MD.read_text(encoding="utf-8")


def test_project_experience_evidence_pack_skill_exists_and_bounded(skill_text: str) -> None:
    assert _SKILL_MD.is_file(), f"File does not exist: {_SKILL_MD}"
    assert len(skill_text) <= _MAX_SKILL_CHARS, (
        f"project-experience-evidence-pack SKILL.md exceeded {_MAX_SKILL_CHARS} characters: {len(skill_text)}"
    )


def test_project_experience_evidence_pack_skill_contains_six_phases(skill_text: str) -> None:
    for marker in _CORE_MODULE_MARKERS:
        assert marker in skill_text, f"Missing core module marker '{marker}' in SKILL.md"


def test_project_experience_evidence_pack_safety_markers(skill_text: str) -> None:
    for marker in _SAFETY_CONTRACT_MARKERS:
        assert marker in skill_text, f"Missing safety contract marker '{marker}' in SKILL.md"
