"""Integration: factory runtime skill allowlist → default_skill_instances map."""

from __future__ import annotations

from pathlib import Path

import pytest
from myrm_agent_harness.backends.skills.state_manager import SkillStateManager

from app.services.agent.skill_instance_resolver import (
    resolve_runtime_skill_instance_bindings,
)


@pytest.fixture
def state_manager(tmp_path: Path) -> SkillStateManager:
    return SkillStateManager(base_dir=str(tmp_path / ".myrm"))


def test_runtime_allowlist_maps_skill_id_to_explicit_instance(
    state_manager: SkillStateManager,
) -> None:
    """Mirrors factory.py skill_id_to_name + runtime_skill_ids wiring."""
    state_manager.create_instance("github_skill", "work")
    state_manager.create_instance("github_skill", "personal")

    skill_id_to_name = {
        "prebuilt::github": "github_skill",
        "github_skill": "github_skill",
    }

    bindings = resolve_runtime_skill_instance_bindings(
        runtime_skill_ids=["prebuilt::github"],
        skill_configs={"prebuilt::github": {"instance_name": "work", "is_core": True}},
        skill_id_to_name=skill_id_to_name,
        state_manager=state_manager,
    )

    assert bindings == {"github_skill": "work"}


def test_runtime_allowlist_skips_unlisted_skills(
    state_manager: SkillStateManager,
) -> None:
    state_manager.create_instance("github_skill", "work")
    state_manager.create_instance("notion_skill", "solo")

    skill_id_to_name = {
        "github": "github_skill",
        "notion": "notion_skill",
    }

    bindings = resolve_runtime_skill_instance_bindings(
        runtime_skill_ids=["github"],
        skill_configs={
            "github": {"instance_name": "work"},
            "notion": {"instance_name": "solo"},
        },
        skill_id_to_name=skill_id_to_name,
        state_manager=state_manager,
    )

    assert bindings == {"github_skill": "work"}
