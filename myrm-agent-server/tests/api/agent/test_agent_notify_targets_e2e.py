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


@pytest.mark.asyncio
async def test_notify_targets_flows_to_profile_resolver(async_client: AsyncClient) -> None:
    """API persist → profile_resolver.resolve() → factory-ready notify_targets tuple."""
    from app.services.agent.profile_resolver import get_agent_profile_resolver

    create_payload = {
        "name": "Resolver Notify Agent",
        "system_prompt": "Notify resolver test.",
        "model_selection": {"providerId": "openai", "model": "gpt-4o-mini"},
        "notify_targets": [
            {"channel": "telegram", "recipient_id": "chat_resolver"},
            {"channel": "slack"},
        ],
    }
    response = await async_client.post("/api/agents", json=create_payload)
    assert response.status_code == 200
    agent_id = response.json()["data"]["id"]

    resolver = get_agent_profile_resolver()
    resolver.invalidate(agent_id)
    resolved = await resolver.resolve(agent_id)
    assert resolved is not None
    assert resolved.notify_targets == ({"channel": "telegram", "recipient_id": "chat_resolver"},)

    deferred_tools: list[object] = []
    if resolved.notify_targets:
        from app.services.agent.outbound_notify import (
            create_channel_notify_tool,
            create_notification_sender,
        )

        sender_result = create_notification_sender(resolved.notify_targets)
        assert sender_result is not None
        sender, notify_config = sender_result
        deferred_tools.append(create_channel_notify_tool(sender, notify_config))

    assert len(deferred_tools) == 1
    assert getattr(deferred_tools[0], "name", None) == "channel_notify_tool"

    await async_client.delete(f"/api/agents/{agent_id}")


@pytest.mark.asyncio
async def test_profile_resolver_empty_notify_skips_factory_tool(async_client: AsyncClient) -> None:
    from app.services.agent.profile_resolver import get_agent_profile_resolver

    response = await async_client.post(
        "/api/agents",
        json={
            "name": "No Notify Resolver Agent",
            "system_prompt": "No notify.",
            "model_selection": {"providerId": "openai", "model": "gpt-4o-mini"},
        },
    )
    assert response.status_code == 200
    agent_id = response.json()["data"]["id"]

    resolver = get_agent_profile_resolver()
    resolver.invalidate(agent_id)
    resolved = await resolver.resolve(agent_id)
    assert resolved is not None
    assert resolved.notify_targets == ()

    deferred_tools: list[object] = []
    if resolved.notify_targets:
        deferred_tools.append(object())

    assert deferred_tools == []

    await async_client.delete(f"/api/agents/{agent_id}")
