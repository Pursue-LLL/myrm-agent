"""Architecture guard: WorkBuddy Top 20 essential skills migration map integrity.

[INPUT]
- assets/migration_maps/workbuddy_top20_skills_map.json
- assets/prebuilt_skills/
- assets/prebuilt_agents/

[OUTPUT]
- Architecture tests ensuring:
  1. The migration map contains exactly 20 structured entries.
  2. Every entry defines id, name, workbuddy_name, myrm_skill_id, myrm_agent_template, category, and description.
  3. Every myrm_skill_id points to an existing prebuilt skill in assets/prebuilt_skills/.
  4. Every myrm_agent_template maps to an existing prebuilt agent in assets/prebuilt_agents/ (or is registered).
"""

from __future__ import annotations

import json
from pathlib import Path

_SERVER_ROOT = Path(__file__).resolve().parents[2]
_MAP_FILE = _SERVER_ROOT / "assets" / "migration_maps" / "workbuddy_top20_skills_map.json"
_SKILLS_DIR = _SERVER_ROOT / "assets" / "prebuilt_skills"
_AGENTS_DIR = _SERVER_ROOT / "assets" / "prebuilt_agents"


def test_migration_map_file_exists() -> None:
    assert _MAP_FILE.is_file(), f"Migration map file does not exist at {_MAP_FILE}"


def test_migration_map_contains_exactly_20_skills() -> None:
    data = json.loads(_MAP_FILE.read_text(encoding="utf-8"))
    assert isinstance(data, list)
    assert len(data) == 20, f"Expected 20 entries in top 20 migration map, found {len(data)}"


def test_migration_map_schema_and_prebuilt_links() -> None:
    data = json.loads(_MAP_FILE.read_text(encoding="utf-8"))
    required_fields = {
        "id",
        "name",
        "workbuddy_name",
        "myrm_skill_id",
        "myrm_agent_template",
        "category",
        "description",
    }

    for item in data:
        missing = required_fields - set(item.keys())
        assert not missing, f"Item {item.get('id')} missing fields: {missing}"

        # Verify skill exists
        skill_id = item["myrm_skill_id"]
        skill_dir = _SKILLS_DIR / skill_id
        assert skill_dir.is_dir(), f"Referenced skill '{skill_id}' does not exist in {_SKILLS_DIR}"
        skill_md = skill_dir / "SKILL.md"
        assert skill_md.is_file(), f"Skill '{skill_id}' missing SKILL.md"

        # Verify agent template exists
        agent_id = item["myrm_agent_template"]
        agent_yaml = _AGENTS_DIR / f"{agent_id}.yaml"
        assert agent_yaml.is_file(), f"Referenced agent template '{agent_id}' does not exist in {_AGENTS_DIR}"


def test_workbuddy_migration_resolver() -> None:
    from app.core.skills.marketplace.workbuddy_migration import (
        WORKBUDDY_TOP_20_MIGRATION_MAP,
        resolve_workbuddy_migration_target,
    )

    assert len(WORKBUDDY_TOP_20_MIGRATION_MAP) == 20
    resolved = resolve_workbuddy_migration_target("wb_host_ops")
    assert resolved is not None
    assert resolved["myrm_skill_id"] == "host-server-ops"

    assert resolve_workbuddy_migration_target("non_existent_skill_xyz") is None

