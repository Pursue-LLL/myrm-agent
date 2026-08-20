"""Integration tests for evaluate-action-space API."""

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
async def async_client(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


def _assert_catalog_preview_shape(result: dict[str, object]) -> None:
    preview = result["catalog_preview"]
    assert isinstance(preview, dict)
    assert preview["inline_count"] == 0
    assert preview["hidden_count"] == 0
    assert preview["search_mounted"] is False
    assert preview["inline_cap"] == 20


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
