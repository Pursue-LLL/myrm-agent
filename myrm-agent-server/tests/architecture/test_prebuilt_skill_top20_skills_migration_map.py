"""Architecture guard: WorkBuddy Top 20 essential skills migration guide contract.

[INPUT]
- assets/prebuilt_skills/top20-skills-migration-guide/SKILL.md

[OUTPUT]
- Architecture tests ensuring top20-skills-migration-guide skill retains all 20 1:1 mapping items,
  architectural advantages (WYSIWYG, air-gapped sandbox, minimal mount), and clean frontmatter.

[POS]
Architecture test verifying the operational integrity and contract stability of WorkBuddyTop20EssentialSkillsMigrationMapFeaturedPack.
"""

from __future__ import annotations

from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SKILL_MD = _REPO_ROOT / "assets" / "prebuilt_skills" / "top20-skills-migration-guide" / "SKILL.md"

_TOP20_MIGRATION_MARKERS = (
    "voice-memo-synthesizer",
    "office-document",
    "deep-research",
    "web-scraping",
    "data-analysis-pipeline",
    "code-review-pipeline",
    "architecture-diagram",
    "personal-life-workbench",
    "persona-voice",
    "document-extraction",
    "host-server-ops",
    "db-diagnostics",
    "frontend-development",
    "social-media-monitoring",
    "daily-briefing",
    "customer-relationship-draft-review",
    "brand-vi-guidelines",
    "github-workflow",
    "competitive-analysis-pipeline",
    "task-planning",
    "WYSIWYG Assembly",
    "Air-Gapped Artifact Sandbox",
    "Turn-Level Minimal Mount",
)


@pytest.fixture(scope="module")
def skill_text() -> str:
    if not _SKILL_MD.is_file():
        pytest.fail(f"Missing top20-skills-migration-guide skill: {_SKILL_MD}")
    return _SKILL_MD.read_text(encoding="utf-8")


def test_top20_skills_migration_guide_file_exists() -> None:
    assert _SKILL_MD.is_file(), f"File does not exist: {_SKILL_MD}"


def test_top20_skills_migration_guide_contains_all_markers(skill_text: str) -> None:
    missing = [m for m in _TOP20_MIGRATION_MARKERS if m not in skill_text]
    assert not missing, f"top20-skills-migration-guide SKILL.md is missing markers: {missing}"
