"""API tests for channel pairings (AgentNotifyTargets data source)."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
async def async_client(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


@pytest.mark.asyncio
async def test_list_pairings_returns_list(async_client: AsyncClient) -> None:
    response = await async_client.get("/api/channels/manage/pairings")
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)


@pytest.mark.asyncio
async def test_create_and_list_pairing(async_client: AsyncClient) -> None:
    create = await async_client.post(
        "/api/channels/manage/pairings",
        json={"channel": "telegram", "sender_id": "integration_chat_999"},
    )
    assert create.status_code in (200, 201)
    created = create.json()
    assert created["channel"] == "telegram"
    assert created["sender_id"] == "integration_chat_999"

    listed = (await async_client.get("/api/channels/manage/pairings")).json()
    assert any(p.get("sender_id") == "integration_chat_999" for p in listed)

    await async_client.delete(f"/api/channels/manage/pairings/{created['id']}")
