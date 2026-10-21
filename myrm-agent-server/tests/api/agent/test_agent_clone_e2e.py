"""端到端集成测试：Agent 克隆，以及已退役的 JSON 交换通道不再对外提供。

专家之间的交换格式只有 Agent Plugins ZIP（见 tests/api/plugins、tests/services/plugins）；
这里覆盖仍保留的克隆端点，并守住 JSON 导入导出与工作区文件束路由不会回来。
"""

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
async def async_client(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


@pytest.mark.asyncio
async def test_agent_clone_e2e(async_client: AsyncClient):
    """Test one-click agent cloning with proper isolation."""

    create_data = {
        "name": "Clone Source Agent",
        "description": "Agent to be cloned",
        "system_prompt": "You are the original.",
        "home_directory": "/tmp/test-agent-home",
        "avatar_url": "home://avatar.png",
        "mcp_ids": ["mcp-clone"],
        "skill_ids": ["skill-clone"],
        "is_built_in": False,
    }

    response = await async_client.post("/api/agents", json=create_data)
    assert response.status_code == 200
    source_id = response.json()["data"]["id"]

    cloned_ids: list[str] = []
    try:
        # Clone with custom name
        clone_res = await async_client.post(
            f"/api/agents/{source_id}/clone",
            json={"name": "My Custom Clone"},
        )
        assert clone_res.status_code == 200
        cloned = clone_res.json()["data"]
        cloned_ids.append(cloned["id"])

        assert cloned["id"] != source_id
        assert cloned["name"] == "My Custom Clone"
        assert cloned["is_built_in"] is False
        assert cloned["home_directory"] is None
        assert cloned["avatar_url"] is None
        assert cloned["mcp_ids"] == ["mcp-clone"]
        assert cloned["skill_ids"] == ["skill-clone"]

        # The response hides the system prompt; the stored copy keeps it.
        stored = await async_client.get(f"/api/agents/{cloned['id']}", params={"show_system_prompt": "true"})
        assert stored.json()["data"]["system_prompt"] == "You are the original."

        # Clone without custom name (default "... (Copy)")
        clone_res2 = await async_client.post(f"/api/agents/{source_id}/clone")
        assert clone_res2.status_code == 200
        cloned2 = clone_res2.json()["data"]
        cloned_ids.append(cloned2["id"])
        assert cloned2["name"] == "Clone Source Agent (Copy)"

        # Clone non-existent agent
        clone_404 = await async_client.post(
            "/api/agents/non-existent-id/clone",
            json={"name": "Should fail"},
        )
        assert clone_404.status_code == 404

    finally:
        for cid in cloned_ids:
            await async_client.delete(f"/api/agents/{cid}")
        await async_client.delete(f"/api/agents/{source_id}")


RETIRED_ROUTES = (
    ("GET", "/api/agents/some-agent/export"),
    ("POST", "/api/agents/import"),
    ("GET", "/api/agents/some-agent/bundle"),
    ("POST", "/api/agents/some-agent/bundle/sync-to-workspace"),
    ("POST", "/api/agents/some-agent/bundle/sync-from-workspace"),
    ("POST", "/api/agents/bundle/import-from-workspace"),
)


@pytest.mark.asyncio
@pytest.mark.parametrize(("method", "path"), RETIRED_ROUTES)
async def test_retired_exchange_routes_are_not_served(async_client: AsyncClient, method: str, path: str):
    """JSON export/import and workspace bundles are gone; nothing may answer on those paths."""
    response = await async_client.request(method, path, json={} if method == "POST" else None)

    assert response.status_code in (404, 405), f"{method} {path} is still served: {response.status_code}"
