"""Integration tests for evaluate-action-space API."""

from collections.abc import AsyncIterator
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from myrm_agent_harness.agent.tool_management.action_space import ActionSpaceProfiler

from app.core.skills.models import Skill
from app.core.storage.types import SkillType


@pytest.fixture
async def async_client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


def _assert_catalog_preview_shape(result: dict[str, object]) -> None:
    preview = result["catalog_preview"]
    assert isinstance(preview, dict)
    assert preview == {
        "inline_count": 0,
        "hidden_count": 0,
        "overflow_count": 0,
        "catalog_tokens": 0,
        "search_mounted": False,
    }


@pytest.mark.asyncio
async def test_evaluate_action_space_basic(
    async_client: AsyncClient,
) -> None:
    """Test the evaluate-action-space endpoint with basic input."""
    payload = {
        "skill_ids": [],
        "skill_configs": {},
        "mcp_servers": ["github", "jira"],
        "enabled_builtin_tools": ["web_search"],
    }

    response = await async_client.post("/api/agents/evaluate-action-space", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True

    result = data["data"]
    # 2 MCPs (400 each) + 1 Builtin (100) = 900
    assert result["ascs_score"] == 900
    assert result["max_safe_score"] == 1500

    # 900 / 1500 = 0.6 -> noise level 60%
    # accuracy = 100 - 60 = 40%
    assert result["accuracy_level"] == 40
    assert result["is_high"] is True
    assert result["is_critical"] is False
    _assert_catalog_preview_shape(result)


@pytest.mark.asyncio
async def test_evaluate_action_space_critical(
    async_client: AsyncClient,
) -> None:
    """Test the evaluate-action-space endpoint triggering critical state."""
    payload = {
        "skill_ids": [],
        "skill_configs": {},
        "mcp_servers": ["github", "jira", "slack", "confluence"],  # 1600
        "enabled_builtin_tools": [],
    }

    response = await async_client.post("/api/agents/evaluate-action-space", json=payload)

    assert response.status_code == 200
    data = response.json()

    result = data["data"]
    assert result["ascs_score"] == 1600
    assert result["accuracy_level"] == 0  # maxes out at 100% noise
    assert result["is_critical"] is True


def _skill(skill_id: str, name: str, description: str) -> Skill:
    return Skill(
        id=skill_id,
        type=SkillType.PREBUILT,
        name=name,
        description=description,
        storage_path=f"/tmp/{skill_id}",
    )


@pytest.mark.asyncio
async def test_evaluate_action_space_scores_the_selected_skills(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Selected skills are resolved through the skills service; a non-core skill costs half; the preview covers the same selection."""
    skills = [
        _skill("skill-core", "core-skill", "a" * 100),
        _skill("skill-side", "side-skill", "b" * 200),
    ]
    monkeypatch.setattr(
        "app.core.skills.store.service.skills_service.get_skills_by_ids",
        AsyncMock(return_value=skills),
    )
    # The preview numbers have their own tests (`test_build_catalog_preview.py`); here only the wiring is checked.
    preview = {"inline_count": 1, "hidden_count": 1, "overflow_count": 0, "catalog_tokens": 321, "search_mounted": True}
    preview_inputs: list[tuple[list[str], dict[str, dict[str, object]]]] = []

    async def _build_preview(skill_ids: list[str], skill_configs: dict[str, dict[str, object]]) -> dict[str, int | bool]:
        preview_inputs.append((skill_ids, skill_configs))
        return preview

    monkeypatch.setattr("app.api.agents.agent_extras._build_catalog_preview", _build_preview)
    payload = {
        "skill_ids": [skill.id for skill in skills],
        "skill_configs": {"skill-core": {"is_core": True}, "skill-side": {"is_core": False}},
        "mcp_servers": [],
        "enabled_builtin_tools": [],
    }

    response = await async_client.post("/api/agents/evaluate-action-space", json=payload)

    assert response.status_code == 200, response.text
    result = response.json()["data"]
    base = ActionSpaceProfiler.BASE_TOOL_COST
    assert result["ascs_score"] == (base + 100 // 50) + int((base + 200 // 50) * 0.5)
    assert result["catalog_preview"] == preview
    assert preview_inputs == [(payload["skill_ids"], payload["skill_configs"])]
