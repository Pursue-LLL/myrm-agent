"""E2E tests for Agent profile snapshot / rollback HTTP APIs."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

API_PREFIX = "/api/agents"


@pytest.fixture
async def async_client(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


async def _create_agent(client: AsyncClient) -> str:
    response = await client.post(
        f"{API_PREFIX}",
        json={
            "name": "Snapshot API Agent",
            "description": "For snapshot API e2e",
            "system_prompt": "Original prompt for snapshot tests.",
            "skill_ids": [],
            "mcp_ids": [],
        },
    )
    assert response.status_code == 200
    return response.json()["data"]["id"]


@pytest.mark.asyncio
async def test_snapshot_api_list_rollback_and_snapshot_saved(
    async_client: AsyncClient,
) -> None:
    agent_id = await _create_agent(async_client)

    list_res = await async_client.get(f"{API_PREFIX}/{agent_id}/snapshots")
    assert list_res.status_code == 200
    assert list_res.json()["data"] == []

    update_res = await async_client.put(
        f"{API_PREFIX}/{agent_id}",
        json={"system_prompt": "Updated prompt after first save."},
    )
    assert update_res.status_code == 200
    updated = update_res.json()["data"]
    assert updated["snapshot_count"] >= 1
    assert updated["snapshot_saved"] is True

    list_res = await async_client.get(f"{API_PREFIX}/{agent_id}/snapshots")
    snapshots = list_res.json()["data"]
    assert len(snapshots) >= 1

    rollback_res = await async_client.post(f"{API_PREFIX}/{agent_id}/rollback")
    assert rollback_res.status_code == 200

    detail_res = await async_client.get(f"{API_PREFIX}/{agent_id}?show_system_prompt=true")
    assert detail_res.status_code == 200
    assert "Original prompt" in detail_res.json()["data"]["system_prompt"]


@pytest.mark.asyncio
async def test_snapshot_api_rollback_to_id_keeps_pre_rollback(
    async_client: AsyncClient,
) -> None:
    agent_id = await _create_agent(async_client)

    await async_client.put(
        f"{API_PREFIX}/{agent_id}",
        json={"system_prompt": "Mutation one."},
    )
    first_list = (await async_client.get(f"{API_PREFIX}/{agent_id}/snapshots")).json()["data"]
    assert len(first_list) >= 1
    target_id = first_list[-1]["id"]

    await async_client.put(
        f"{API_PREFIX}/{agent_id}",
        json={"system_prompt": "Mutation two."},
    )

    restore_res = await async_client.post(f"{API_PREFIX}/{agent_id}/rollback/{target_id}")
    assert restore_res.status_code == 200

    after_list = (await async_client.get(f"{API_PREFIX}/{agent_id}/snapshots")).json()["data"]
    pre_rollbacks = [item for item in after_list if item.get("reason") == "pre-rollback"]
    assert len(pre_rollbacks) == 1
    assert pre_rollbacks[0]["snapshot_data"]["system_prompt"] == "Mutation two."

    detail_res = await async_client.get(f"{API_PREFIX}/{agent_id}?show_system_prompt=true")
    assert "Original prompt" in detail_res.json()["data"]["system_prompt"]


@pytest.mark.asyncio
async def test_snapshot_api_rollback_without_snapshot_returns_400(
    async_client: AsyncClient,
) -> None:
    agent_id = await _create_agent(async_client)
    response = await async_client.post(f"{API_PREFIX}/{agent_id}/rollback")
    assert response.status_code == 400
