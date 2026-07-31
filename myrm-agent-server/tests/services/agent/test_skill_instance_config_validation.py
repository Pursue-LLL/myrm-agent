"""Tests for Agent skill_configs.instance_name save validation."""

from __future__ import annotations

from pathlib import Path

import pytest
from myrm_agent_harness.backends.skills.state_manager import SkillStateManager

from app.services.agent.skill_instance_resolver import (
    SkillConfigValidationError,
    serialize_agent_skill_configs,
    validate_agent_skill_config_instances,
)


@pytest.fixture
def state_manager(tmp_path: Path) -> SkillStateManager:
    return SkillStateManager(base_dir=str(tmp_path / ".myrm"))


@pytest.mark.asyncio
async def test_validate_accepts_existing_instance(state_manager: SkillStateManager) -> None:
    state_manager.create_instance("github", "work")

    await validate_agent_skill_config_instances(
        skill_configs={"github": {"instance_name": "work"}},
        state_manager=state_manager,
        skill_id_to_name={"github": "github"},
    )


@pytest.mark.asyncio
async def test_validate_rejects_missing_instance(state_manager: SkillStateManager) -> None:
    state_manager.create_instance("github", "work")

    with pytest.raises(SkillConfigValidationError) as exc:
        await validate_agent_skill_config_instances(
            skill_configs={"github": {"instance_name": "missing"}},
            state_manager=state_manager,
            skill_id_to_name={"github": "github"},
        )

    assert exc.value.skill_id == "github"
    assert exc.value.instance_name == "missing"


@pytest.mark.asyncio
async def test_validate_skips_null_instance_name(state_manager: SkillStateManager) -> None:
    await validate_agent_skill_config_instances(
        skill_configs={"github": {"instance_name": None, "is_core": True}},
        state_manager=state_manager,
        skill_id_to_name={"github": "github"},
    )


@pytest.mark.asyncio
async def test_validate_rejects_missing_instance_pydantic_model(state_manager: SkillStateManager) -> None:
    from app.database.dto import SkillConfig

    state_manager.create_instance("github", "work")

    with pytest.raises(SkillConfigValidationError):
        await validate_agent_skill_config_instances(
            skill_configs={"github": SkillConfig(is_core=True, instance_name="missing")},
            state_manager=state_manager,
            skill_id_to_name={"github": "github"},
        )


@pytest.mark.asyncio
async def test_validate_maps_storage_skill_id(state_manager: SkillStateManager) -> None:
    state_manager.create_instance("github_skill", "personal")

    await validate_agent_skill_config_instances(
        skill_configs={"prebuilt::github": {"instance_name": "personal"}},
        state_manager=state_manager,
        skill_id_to_name={"prebuilt::github": "github_skill"},
    )


def test_serialize_agent_skill_configs_from_pydantic_model() -> None:
    from app.database.dto import SkillConfig

    serialized = serialize_agent_skill_configs(
        {"github": SkillConfig(is_core=True, instance_name="work")},
    )

    assert serialized == {"github": {"is_core": True, "instance_name": "work"}}
