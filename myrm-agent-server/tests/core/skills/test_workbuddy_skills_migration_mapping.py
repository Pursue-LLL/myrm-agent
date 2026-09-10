"""Test suite for WorkBuddy Top 20 essential skills migration mapping.

Ensures all 20 mapped skill IDs point to verified prebuilt skill assets without deadlinks.
"""

from __future__ import annotations

from pathlib import Path
from app.services.migration.workbuddy_skills_mapping import WORKBUDDY_TOP_20_ESSENTIAL_SKILLS_MAP

_REPO_ROOT = Path(__file__).resolve().parents[3]
_PREBUILT_SKILLS_DIR = _REPO_ROOT / "assets" / "prebuilt_skills"


def test_workbuddy_skills_mapping_count() -> None:
    assert len(WORKBUDDY_TOP_20_ESSENTIAL_SKILLS_MAP) == 20


def test_workbuddy_skills_mapping_unique_names() -> None:
    wb_names = [item.wb_skill_name for item in WORKBUDDY_TOP_20_ESSENTIAL_SKILLS_MAP]
    assert len(wb_names) == len(set(wb_names)), "Duplicate WorkBuddy skill names found"


def test_all_mapped_skills_exist_in_prebuilt_skills() -> None:
    for item in WORKBUDDY_TOP_20_ESSENTIAL_SKILLS_MAP:
        skill_file = _PREBUILT_SKILLS_DIR / item.myrm_skill_id / "SKILL.md"
        assert skill_file.is_file(), f"Deadlink mapped skill {item.myrm_skill_id} at {skill_file}"
