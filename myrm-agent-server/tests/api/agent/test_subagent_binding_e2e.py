"""端到端集成测试：Agent subagent_ids binding CRUD

测试 subagent_ids 字段在 Agent 创建、读取、更新、删除的全生命周期中正确持久化。
"""

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
async def async_client(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


@pytest.mark.asyncio
async def test_subagent_ids_crud(async_client: AsyncClient):
    """Test subagent_ids full CRUD lifecycle."""
    helper_resp = await async_client.post(
        "/api/agents",
        json={
            "name": "Helper Agent",
            "description": "Helper for subagent binding test",
        },
    )
    assert helper_resp.status_code == 200
    helper_id = helper_resp.json()["data"]["id"]

    helper2_resp = await async_client.post(
        "/api/agents",
        json={
            "name": "Helper Agent 2",
            "description": "Another helper",
        },
    )
    assert helper2_resp.status_code == 200
    helper2_id = helper2_resp.json()["data"]["id"]

    try:
        # Create with subagent_ids
        create_resp = await async_client.post(
            "/api/agents",
            json={
                "name": "Manager Agent",
                "description": "Manages subagents",
                "subagent_ids": [helper_id],
            },
        )
        assert create_resp.status_code == 200
        created = create_resp.json()["data"]
        manager_id = created["id"]
        assert created["subagent_ids"] == [helper_id]

        # Read back
        get_resp = await async_client.get(f"/api/agents/{manager_id}")
        assert get_resp.status_code == 200
        detail = get_resp.json()["data"]
        assert detail["subagent_ids"] == [helper_id]

        # Update: add second subagent
        update_resp = await async_client.put(
            f"/api/agents/{manager_id}",
            json={
                "subagent_ids": [helper_id, helper2_id],
            },
        )
        assert update_resp.status_code == 200
        updated = update_resp.json()["data"]
        assert set(updated["subagent_ids"]) == {helper_id, helper2_id}

        # Update: remove all subagents
        clear_resp = await async_client.put(
            f"/api/agents/{manager_id}",
            json={
                "subagent_ids": [],
            },
        )
        assert clear_resp.status_code == 200
        cleared = clear_resp.json()["data"]
        assert cleared["subagent_ids"] == []

        # Verify empty persisted
        verify_resp = await async_client.get(f"/api/agents/{manager_id}")
        assert verify_resp.status_code == 200
        assert verify_resp.json()["data"]["subagent_ids"] == []

        # Cleanup manager
        await async_client.delete(f"/api/agents/{manager_id}")

    finally:
        await async_client.delete(f"/api/agents/{helper_id}")
        await async_client.delete(f"/api/agents/{helper2_id}")


@pytest.mark.asyncio
async def test_agent_without_subagent_ids_defaults_empty(async_client: AsyncClient):
    """Agent created without subagent_ids should have empty list."""
    resp = await async_client.post(
        "/api/agents",
        json={
            "name": "No Subagents Agent",
        },
    )
    assert resp.status_code == 200
    created = resp.json()["data"]
    agent_id = created["id"]
    assert created["subagent_ids"] == []

    await async_client.delete(f"/api/agents/{agent_id}")
