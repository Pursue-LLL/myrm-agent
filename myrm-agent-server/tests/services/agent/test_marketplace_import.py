"""Unit tests for marketplace_import module.

Tests cover:
- Full import flow with skill/subagent/agent creation
- Skill ID remapping
- Subagent ID remapping + skill_ids remapping within subagents
- Idempotent subagent de-duplication by name
- Malformed skill handling (skip)
- save_skill failure handling
- Empty package import
- _remap_ids preserves unmapped IDs
"""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@dataclass
class FakeSkillSaveResult:
    success: bool
    skill_id: str = ""
    skill_name: str = ""
    saved_path: str = ""
    was_updated: bool = False
    error: str = ""


@dataclass
class FakeAgentProfile:
    id: str
    display_name: str | None = None


def _make_package(
    *,
    agent_profile: dict | None = None,
    bundled_skills: list[dict] | None = None,
    bundled_subagents: list[dict] | None = None,
) -> dict:
    return {
        "agent_profile": agent_profile or {
            "display_name": "Test Agent",
            "description": "desc",
            "system_prompt": "sys",
            "skill_ids": ["old-skill-1"],
            "subagent_ids": ["old-sub-1"],
            "enabled_builtin_tools": [],
            "personality_style": "professional",
        },
        "bundled_skills": bundled_skills if bundled_skills is not None else [
            {
                "id": "old-skill-1",
                "name": "sales-skill",
                "content": "# Sales Skill\nPrompt here.",
                "description": "Sales helper",
                "resources": {"data.json": '{"key": "val"}'},
            },
        ],
        "bundled_subagents": bundled_subagents if bundled_subagents is not None else [
            {
                "original_id": "old-sub-1",
                "profile": {
                    "display_name": "Sub Agent",
                    "description": "sub desc",
                    "system_prompt": "sub sys",
                    "skill_ids": ["old-skill-1"],
                    "enabled_builtin_tools": [],
                },
            },
        ],
    }


@pytest.fixture
def mock_skill_svc() -> AsyncMock:
    svc = AsyncMock()
    svc.save_skill = AsyncMock(return_value=FakeSkillSaveResult(
        success=True,
        skill_id="local::new-skill-hash",
        skill_name="sales-skill",
    ))
    svc.write_resource = AsyncMock()
    return svc


_AGENT_SVC_PATH = "app.services.agent.agent_service.AgentService"


@pytest.fixture
def patch_agent_service():
    """Patch AgentService class methods used by marketplace_import."""
    with patch(
        f"{_AGENT_SVC_PATH}.get_agent_by_name",
        new_callable=AsyncMock,
        return_value=None,
    ), patch(
        f"{_AGENT_SVC_PATH}.create_agent",
        new_callable=AsyncMock,
        side_effect=lambda data: FakeAgentProfile(
            id=f"new-{data.name.lower().replace(' ', '-')}",
            display_name=data.name,
        ),
    ):
        yield


@pytest.mark.asyncio
async def test_full_import_flow(mock_skill_svc: AsyncMock, patch_agent_service: None):
    """Full import: skills installed, IDs remapped, subagent + agent created."""
    from app.services.agent.marketplace_import import import_agent_package

    package = _make_package()
    result = await import_agent_package(mock_skill_svc, package)

    mock_skill_svc.save_skill.assert_called_once_with(
        "sales-skill", "# Sales Skill\nPrompt here.", "Sales helper"
    )
    mock_skill_svc.write_resource.assert_called_once_with(
        "sales-skill", "data.json", '{"key": "val"}'
    )
    assert result == "new-test-agent"


@pytest.mark.asyncio
async def test_skill_id_remapping(mock_skill_svc: AsyncMock, patch_agent_service: None):
    """Agent's skill_ids are remapped from old to new IDs."""
    from app.services.agent.agent_service import AgentService
    from app.services.agent.marketplace_import import import_agent_package

    package = _make_package(bundled_subagents=[])
    created_data: list = []

    original_create = AgentService.create_agent

    async def capture_create(data):
        created_data.append(data)
        return FakeAgentProfile(id="new-agent", display_name=data.name)

    with patch.object(AgentService, "create_agent", side_effect=capture_create):
        await import_agent_package(mock_skill_svc, package)

    assert len(created_data) == 1
    assert created_data[0].skill_ids == ["local::new-skill-hash"]


@pytest.mark.asyncio
async def test_subagent_skill_ids_remapped(mock_skill_svc: AsyncMock, patch_agent_service: None):
    """Subagent's skill_ids also get remapped."""
    from app.services.agent.agent_service import AgentService
    from app.services.agent.marketplace_import import import_agent_package

    package = _make_package()
    created_data: list = []

    async def capture_create(data):
        created_data.append(data)
        return FakeAgentProfile(
            id=f"new-{data.name.lower().replace(' ', '-')}",
            display_name=data.name,
        )

    with patch.object(AgentService, "create_agent", side_effect=capture_create):
        await import_agent_package(mock_skill_svc, package)

    sub_data = created_data[0]
    assert sub_data.name == "Sub Agent"
    assert sub_data.skill_ids == ["local::new-skill-hash"]


@pytest.mark.asyncio
async def test_subagent_idempotent_dedup(mock_skill_svc: AsyncMock):
    """Existing subagent with same name is reused (not created again)."""
    from app.services.agent.agent_service import AgentService
    from app.services.agent.marketplace_import import import_agent_package

    package = _make_package()
    created_data: list = []

    async def capture_create(data):
        created_data.append(data)
        return FakeAgentProfile(
            id=f"new-{data.name.lower().replace(' ', '-')}",
            display_name=data.name,
        )

    with patch.object(
        AgentService, "get_agent_by_name",
        new_callable=AsyncMock,
        return_value=FakeAgentProfile(id="existing-sub-id", display_name="Sub Agent"),
    ), patch.object(AgentService, "create_agent", side_effect=capture_create):
        result = await import_agent_package(mock_skill_svc, package)

    main_agent_data = created_data[0]
    assert main_agent_data.name == "Test Agent"
    assert "existing-sub-id" in main_agent_data.subagent_ids


@pytest.mark.asyncio
async def test_malformed_skill_skipped(mock_skill_svc: AsyncMock, patch_agent_service: None):
    """Skills without name or content are skipped."""
    from app.services.agent.marketplace_import import import_agent_package

    package = _make_package(
        bundled_skills=[
            {"id": "bad-1", "name": "", "content": "has content"},
            {"id": "bad-2", "name": "has-name", "content": ""},
        ],
        bundled_subagents=[],
    )
    await import_agent_package(mock_skill_svc, package)
    mock_skill_svc.save_skill.assert_not_called()


@pytest.mark.asyncio
async def test_save_skill_failure_handled(mock_skill_svc: AsyncMock, patch_agent_service: None):
    """If save_skill fails, the skill is skipped but import continues."""
    from app.services.agent.agent_service import AgentService
    from app.services.agent.marketplace_import import import_agent_package

    mock_skill_svc.save_skill = AsyncMock(
        return_value=FakeSkillSaveResult(success=False, error="disk full")
    )

    package = _make_package(bundled_subagents=[])
    created_data: list = []

    async def capture_create(data):
        created_data.append(data)
        return FakeAgentProfile(id="new-agent", display_name=data.name)

    with patch.object(AgentService, "create_agent", side_effect=capture_create):
        await import_agent_package(mock_skill_svc, package)

    assert created_data[0].skill_ids == ["old-skill-1"]


@pytest.mark.asyncio
async def test_empty_package(mock_skill_svc: AsyncMock, patch_agent_service: None):
    """Empty package creates agent with defaults."""
    from app.services.agent.marketplace_import import import_agent_package

    package = _make_package(
        agent_profile={"display_name": "Empty Agent"},
        bundled_skills=[],
        bundled_subagents=[],
    )
    result = await import_agent_package(mock_skill_svc, package)
    assert result == "new-empty-agent"
    mock_skill_svc.save_skill.assert_not_called()


@pytest.mark.asyncio
async def test_remap_ids_preserves_unmapped():
    """_remap_ids preserves IDs not in the mapping."""
    from app.services.agent.marketplace_import import _remap_ids

    profile = {
        "skill_ids": ["mapped-1", "unknown-2"],
        "subagent_ids": ["mapped-sub", "unknown-sub"],
    }
    skill_map = {"mapped-1": "new-1"}
    sub_map = {"mapped-sub": "new-sub"}

    result = _remap_ids(profile, skill_map, sub_map)

    assert result["skill_ids"] == ["new-1", "unknown-2"]
    assert result["subagent_ids"] == ["new-sub", "unknown-sub"]
