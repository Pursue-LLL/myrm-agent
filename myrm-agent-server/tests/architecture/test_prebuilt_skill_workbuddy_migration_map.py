"""Architecture guard: workbuddy-migration-map skill must preserve its core operating contract.

[INPUT]
- assets/prebuilt_skills/workbuddy-migration-map/SKILL.md

[OUTPUT]
- Architecture tests ensuring workbuddy-migration-map skill retains all 20 canonical WorkBuddy
  to Myrm capability mappings and 3-phase activation protocol.

[POS]
Architecture test verifying the operational integrity and contract stability of the workbuddy-migration-map prebuilt skill.
"""

from __future__ import annotations

from pathlib import Path

import pytest

_SKILL_MD = (
    Path(__file__).resolve().parents[2]
    / "assets"
    / "prebuilt_skills"
    / "workbuddy-migration-map"
    / "SKILL.md"
)

_CORE_MODULE_MARKERS = (
    "workbuddy-migration-map",
    "Canonical Top 20 Migration Matrix",
    "voice-memo-synthesizer",
    "content-humanizer",
    "office-document",
    "ppt-outline-quality-gate",
    "personal-life-workbench",
    "brand-vi-guidelines",
    "customer-relationship-draft-review",
    "relationship-signal-promoter",
    "project-experience-evidence-pack",
    "enterprise-branded-office",
    "persona-corpus-distillation",
    "competitive-analysis-pipeline",
    "arxiv-research",
    "structure-planner",
    "code-review-pipeline",
    "lean-coding",
    "video-production-pipeline",
    "web-scraping",
    "db-diagnostics",
    "obsidian-notes",
)

_SAFETY_CONTRACT_MARKERS = (
    # Three-phase migration protocol
    "Phase 1: WorkBuddy Skill Identification",
    "Phase 2: Capability Equivalence & Preflight",
    "Phase 3: Execution Guidance & Activation",
    # Verification criteria
    "top_20_skills_mapped",
    "zero_config_activation_documented",
)

_MAX_SKILL_CHARS = 12_000


@pytest.fixture(scope="module")
def skill_text() -> str:
    if not _SKILL_MD.is_file():
        pytest.fail(f"Missing workbuddy-migration-map skill: {_SKILL_MD}")
    return _SKILL_MD.read_text(encoding="utf-8")


def test_workbuddy_migration_map_skill_exists_and_bounded(skill_text: str) -> None:
    assert _SKILL_MD.is_file(), f"File does not exist: {_SKILL_MD}"
    assert len(skill_text) <= _MAX_SKILL_CHARS, (
        f"workbuddy-migration-map SKILL.md is {len(skill_text)} chars, exceeding {_MAX_SKILL_CHARS}"
    )


def test_workbuddy_migration_map_contains_all_20_counterparts(skill_text: str) -> None:
    missing = [m for m in _CORE_MODULE_MARKERS if m not in skill_text]
    assert not missing, f"workbuddy-migration-map SKILL.md is missing mapped skills: {missing}"


def test_workbuddy_migration_map_contains_safety_contract_markers(skill_text: str) -> None:
    missing = [m for m in _SAFETY_CONTRACT_MARKERS if m not in skill_text]
    assert not missing, f"workbuddy-migration-map SKILL.md is missing safety contract markers: {missing}"
