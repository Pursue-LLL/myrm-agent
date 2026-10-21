"""Tests for Agent skill instance binding resolver."""

from __future__ import annotations

from pathlib import Path

import pytest
from myrm_agent_harness.backends.skills.state_manager import SkillStateManager

from app.services.agent.skill_instance_resolver import resolve_skill_instance_bindings


@pytest.fixture
def state_manager(tmp_path: Path) -> SkillStateManager:
    return SkillStateManager(base_dir=str(tmp_path / ".myrm"))


def test_explicit_agent_binding_wins(state_manager: SkillStateManager) -> None:
    state_manager.create_instance("github", "personal")
    state_manager.create_instance("github", "work")

    bindings = resolve_skill_instance_bindings(
        target_skill_names=["github"],
        skill_configs={"github": {"instance_name": "work"}},
        skill_id_to_name={"github": "github"},
        state_manager=state_manager,
    )

    assert bindings == {"github": "work"}


def test_singleton_auto_bind(state_manager: SkillStateManager) -> None:
    state_manager.create_instance("notion", "solo")

    bindings = resolve_skill_instance_bindings(
        target_skill_names=["notion"],
        skill_configs=None,
        skill_id_to_name={"notion": "notion"},
        state_manager=state_manager,
    )

    assert bindings == {"notion": "solo"}


def test_default_instance_name_auto_bind(state_manager: SkillStateManager) -> None:
    state_manager.create_instance("slack", "personal")
    state_manager.create_instance("slack", "default")

    bindings = resolve_skill_instance_bindings(
        target_skill_names=["slack"],
        skill_configs=None,
        skill_id_to_name={"slack": "slack"},
        state_manager=state_manager,
    )

    assert bindings == {"slack": "default"}


def test_multi_instance_without_binding_skipped(state_manager: SkillStateManager) -> None:
    state_manager.create_instance("jira", "a")
    state_manager.create_instance("jira", "b")

    bindings = resolve_skill_instance_bindings(
        target_skill_names=["jira"],
        skill_configs=None,
        skill_id_to_name={"jira": "jira"},
        state_manager=state_manager,
    )

    assert bindings == {}


def test_invalid_explicit_binding_falls_back_to_singleton(
    state_manager: SkillStateManager,
) -> None:
    state_manager.create_instance("linear", "only")

    bindings = resolve_skill_instance_bindings(
        target_skill_names=["linear"],
        skill_configs={"linear": {"instance_name": "missing"}},
        skill_id_to_name={"linear": "linear"},
        state_manager=state_manager,
    )

    assert bindings == {"linear": "only"}


def test_skill_id_maps_to_name(state_manager: SkillStateManager) -> None:
    state_manager.create_instance("github_skill", "work")

    bindings = resolve_skill_instance_bindings(
        target_skill_names=["github_skill"],
        skill_configs={"prebuilt::github": {"instance_name": "work"}},
        skill_id_to_name={
            "prebuilt::github": "github_skill",
            "github_skill": "github_skill",
        },
        state_manager=state_manager,
    )

    assert bindings == {"github_skill": "work"}
