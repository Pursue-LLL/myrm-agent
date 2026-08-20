"""Tests for Shared Skill Pool Cross-Agent HotSync, provenance tracking, and orphan cleanup."""

from __future__ import annotations

import pytest

from app.core.skills.discovery.adopt import (
    remove_skill_from_all_agents,
    sync_skill_to_agents,
)
from app.core.skills.models import Skill, SkillType
from app.database.dto import AgentCreate
from app.services.agent.agent_service import AgentService


def test_skill_model_installed_from_roundtrip() -> None:
    """Test Skill installed_from field serialization and deserialization."""
    provenance = {
        "source": "clawhub",
        "origin_url": "https://clawhub.ai/skills/sample",
        "version": "1.2.0",
        "installed_at": "2026-08-20T12:00:00Z",
    }
    skill = Skill(
        id="local::sample_skill",
        name="sample_skill",
        description="A sample skill",
        skill_type=SkillType.LOCAL,
        installed_from=provenance,
    )
    data = skill.to_dict()
    assert data["installed_from"] == provenance

    restored = Skill.from_dict(data)
    assert restored.installed_from == provenance


@pytest.mark.asyncio
async def test_sync_skill_to_agents_and_orphan_cleanup() -> None:
    """Test syncing a skill into multiple agents' allowlists and orphan cleanup upon removal."""
    # 1. Create two test agents
    agent1 = await AgentService.create_agent(
        AgentCreate(
            name="Agent 1",
            description="Test Agent 1",
            system_prompt="Test",
            skill_ids=["local::base_tool"],
        )
    )
    agent2 = await AgentService.create_agent(
        AgentCreate(
            name="Agent 2",
            description="Test Agent 2",
            system_prompt="Test",
            skill_ids=[],
        )
    )

    try:
        # 2. Sync a new skill to both agents
        target_skill_id = "local::shared_calculator"
        sync_res = await sync_skill_to_agents(
            target_skill_id,
            [agent1.id, agent2.id],
        )
        assert sync_res[agent1.id] is True
        assert sync_res[agent2.id] is True

        # Verify agents have the skill
        updated_a1 = await AgentService.get_agent_by_id(agent1.id)
        updated_a2 = await AgentService.get_agent_by_id(agent2.id)
        assert updated_a1 is not None and target_skill_id in (updated_a1.skill_ids or [])
        assert updated_a2 is not None and target_skill_id in (updated_a2.skill_ids or [])

        # 3. Perform orphan cleanup
        cleaned_count = await remove_skill_from_all_agents(target_skill_id)
        assert cleaned_count == 2

        # Verify skill removed from all agent allowlists
        after_cleanup_a1 = await AgentService.get_agent_by_id(agent1.id)
        after_cleanup_a2 = await AgentService.get_agent_by_id(agent2.id)
        assert after_cleanup_a1 is not None and target_skill_id not in (after_cleanup_a1.skill_ids or [])
        assert after_cleanup_a2 is not None and target_skill_id not in (after_cleanup_a2.skill_ids or [])
    finally:
        # Cleanup test agents
        await AgentService.delete_agent(agent1.id)
        await AgentService.delete_agent(agent2.id)
