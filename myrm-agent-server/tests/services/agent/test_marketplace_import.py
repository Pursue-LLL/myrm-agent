"""Unit tests for marketplace_import module.

Tests cover:
- Full import flow with skill/subagent/agent creation
- Skill ID remapping
- Subagent ID remapping + skill_ids remapping within subagents
- Idempotent subagent de-duplication by name
- Malformed skill handling (skip)
- save_skill failure handling
- Empty package import
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


@pytest.fixture
def mock_agent_service():
    with patch(
        "app.services.agent.agent_service.AgentService.get_agent_by_name",
        new_callable=AsyncMock,
        return_value=None,
    ) as mock_get, patch(
        "app.services.agent.agent_service.AgentService.create_agent",
        new_callable=AsyncMock,
        side_effect=lambda data: FakeAgentProfile(
            id=f"new-{data.name.lower().replace(' ', '-')}",
            display_name=data.name,
        ),
    ) as mock_create:
        yield MagicMock(get_agent_by_name=mock_get, create_agent=mock_create)


@pytest.mark.asyncio
async def test_full_import_flow(mock_skill_svc: AsyncMock, mock_agent_service: MagicMock):
    """Full import: skills installed, IDs remapped, subagent + agent created."""
    from app.services.agent.marketplace_import import import_agent_package

    package = _make_package()

    with patch("app.services.agent.marketplace_import.AgentCreate") as MockCreate:
        MockCreate.side_effect = lambda **kwargs: MagicMock(name=kwargs.get("name", ""), **kwargs)

        result = await import_agent_package(mock_skill_svc, package)

    mock_skill_svc.save_skill.assert_called_once_with(
        "sales-skill", "# Sales Skill\nPrompt here.", "Sales helper"
    )
    mock_skill_svc.write_resource.assert_called_once_with(
        "sales-skill", "data.json", '{"key": "val"}'
    )
    assert result.startswith("new-")


@pytest.mark.asyncio
async def test_skill_id_remapping(mock_skill_svc: AsyncMock, mock_agent_service: MagicMock):
    """Agent's skill_ids are remapped from old to new IDs."""
    from app.services.agent.marketplace_import import import_agent_package

    package = _make_package(bundled_subagents=[])

    with patch("app.services.agent.marketplace_import.AgentCreate") as MockCreate:
        calls: list[dict] = []

        def capture(**kwargs):
            calls.append(kwargs)
            return MagicMock(name=kwargs.get("name", ""), **kwargs)

        MockCreate.side_effect = capture
        await import_agent_package(mock_skill_svc, package)

    assert len(calls) == 1
    assert calls[0]["skill_ids"] == ["local::new-skill-hash"]


@pytest.mark.asyncio
async def test_subagent_skill_ids_remapped(mock_skill_svc: AsyncMock, mock_agent_service: MagicMock):
    """Subagent's skill_ids also get remapped."""
    from app.services.agent.marketplace_import import import_agent_package

    package = _make_package()

    with patch("app.services.agent.marketplace_import.AgentCreate") as MockCreate:
        calls: list[dict] = []

        def capture(**kwargs):
            calls.append(kwargs)
            return MagicMock(name=kwargs.get("name", ""), **kwargs)

        MockCreate.side_effect = capture
        await import_agent_package(mock_skill_svc, package)

    sub_call = calls[0]
    assert sub_call["name"] == "Sub Agent"
    assert sub_call["skill_ids"] == ["local::new-skill-hash"]


@pytest.mark.asyncio
async def test_subagent_idempotent_dedup(mock_skill_svc: AsyncMock):
    """Existing subagent with same name is reused (not created again)."""
    from app.services.agent.marketplace_import import import_agent_package

    with patch(
        "app.services.agent.agent_service.AgentService.get_agent_by_name",
        new_callable=AsyncMock,
        return_value=FakeAgentProfile(id="existing-sub-id", display_name="Sub Agent"),
    ), patch(
        "app.services.agent.agent_service.AgentService.create_agent",
        new_callable=AsyncMock,
        side_effect=lambda data: FakeAgentProfile(
            id=f"new-{data.name.lower().replace(' ', '-')}",
            display_name=data.name,
        ),
    ), patch("app.database.dto.AgentCreate") as MockCreate:
        calls: list[dict] = []

        def capture(**kwargs):
            calls.append(kwargs)
            return MagicMock(name=kwargs.get("name", ""), **kwargs)

        MockCreate.side_effect = capture

        package = _make_package()
        await import_agent_package(mock_skill_svc, package)

    agent_call = calls[0]
    assert "existing-sub-id" in agent_call["subagent_ids"]


@pytest.mark.asyncio
async def test_malformed_skill_skipped(mock_skill_svc: AsyncMock, mock_agent_service: MagicMock):
    """Skills without name or content are skipped."""
    from app.services.agent.marketplace_import import import_agent_package

    package = _make_package(
        bundled_skills=[
            {"id": "bad-1", "name": "", "content": "has content"},
            {"id": "bad-2", "name": "has-name", "content": ""},
        ],
        bundled_subagents=[],
    )

    with patch("app.services.agent.marketplace_import.AgentCreate") as MockCreate:
        MockCreate.side_effect = lambda **kwargs: MagicMock(name=kwargs.get("name", ""), **kwargs)
        await import_agent_package(mock_skill_svc, package)

    mock_skill_svc.save_skill.assert_not_called()


@pytest.mark.asyncio
async def test_save_skill_failure_handled(mock_skill_svc: AsyncMock, mock_agent_service: MagicMock):
    """If save_skill fails, the skill is skipped but import continues."""
    from app.services.agent.marketplace_import import import_agent_package

    mock_skill_svc.save_skill = AsyncMock(
        return_value=FakeSkillSaveResult(success=False, error="disk full")
    )

    package = _make_package(bundled_subagents=[])

    with patch("app.services.agent.marketplace_import.AgentCreate") as MockCreate:
        calls: list[dict] = []

        def capture(**kwargs):
            calls.append(kwargs)
            return MagicMock(name=kwargs.get("name", ""), **kwargs)

        MockCreate.side_effect = capture
        await import_agent_package(mock_skill_svc, package)

    assert calls[0]["skill_ids"] == ["old-skill-1"]


@pytest.mark.asyncio
async def test_empty_package(mock_skill_svc: AsyncMock, mock_agent_service: MagicMock):
    """Empty package creates agent with defaults."""
    from app.services.agent.marketplace_import import import_agent_package

    package = _make_package(
        agent_profile={"display_name": "Empty Agent"},
        bundled_skills=[],
        bundled_subagents=[],
    )

    with patch("app.services.agent.marketplace_import.AgentCreate") as MockCreate:
        MockCreate.side_effect = lambda **kwargs: MagicMock(name=kwargs.get("name", ""), **kwargs)
        result = await import_agent_package(mock_skill_svc, package)

    assert result.startswith("new-")
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
