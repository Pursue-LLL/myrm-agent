"""E2E tests for agent notify_targets CRUD via /api/agents."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
async def async_client(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


@pytest.mark.asyncio
async def test_notify_targets_create_get_update_clear(async_client: AsyncClient) -> None:
    """Full CRUD lifecycle for notify_targets on agent metadata."""
    create_payload = {
        "name": "Notify Target Agent",
        "description": "E2E notify_targets test",
        "system_prompt": "You are a notifier.",
        "model_selection": {"providerId": "openai", "model": "gpt-4o-mini"},
        "notify_targets": [
            {"channel": "telegram", "recipient_id": "chat_111", "label": "Primary TG"},
            {"channel": "slack", "recipient_id": "C222"},
        ],
    }
    response = await async_client.post("/api/agents", json=create_payload)
    assert response.status_code == 200
    agent_id = response.json()["data"]["id"]

    detail = (await async_client.get(f"/api/agents/{agent_id}")).json()["data"]
    assert detail["notify_targets"] == [
        {"channel": "telegram", "recipient_id": "chat_111", "label": "Primary TG"},
        {"channel": "slack", "recipient_id": "C222"},
    ]

    update_payload = {
        "notify_targets": [
            {"channel": "discord", "recipient_id": "guild_333", "label": "Alerts"},
        ],
    }
    updated = (await async_client.put(f"/api/agents/{agent_id}", json=update_payload)).json()["data"]
    assert updated["notify_targets"] == [
        {"channel": "discord", "recipient_id": "guild_333", "label": "Alerts"},
    ]

    cleared = (await async_client.put(f"/api/agents/{agent_id}", json={"notify_targets": None})).json()["data"]
    assert cleared["notify_targets"] is None

    await async_client.delete(f"/api/agents/{agent_id}")


@pytest.mark.asyncio
async def test_notify_targets_omitted_on_create_returns_none(async_client: AsyncClient) -> None:
    """Agents without notify_targets should not expose the field as configured."""
    create_payload = {
        "name": "No Notify Agent",
        "system_prompt": "No channels.",
        "model_selection": {"providerId": "openai", "model": "gpt-4o-mini"},
    }
    response = await async_client.post("/api/agents", json=create_payload)
    assert response.status_code == 200
    agent_id = response.json()["data"]["id"]

    detail = (await async_client.get(f"/api/agents/{agent_id}")).json()["data"]
    assert detail.get("notify_targets") is None

    await async_client.delete(f"/api/agents/{agent_id}")
