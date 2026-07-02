"""API tests for channel pairings (AgentNotifyTargets data source)."""

from __future__ import annotations

import uuid

import httpx
import pytest
from httpx import ASGITransport

from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(preset="channels_local")


@pytest.fixture
async def async_client() -> httpx.AsyncClient:
    async with httpx.AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
        headers={"Content-Type": "application/json"},
        timeout=60.0,
    ) as client:
        yield client


@pytest.mark.asyncio
async def test_list_pairings_returns_list(async_client: httpx.AsyncClient) -> None:
    response = await async_client.get("/api/v1/channels/manage/pairings")
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)


@pytest.mark.asyncio
async def test_create_and_list_pairing(async_client: httpx.AsyncClient) -> None:
    sender_id = f"integration_chat_{uuid.uuid4().hex[:8]}"
    create = await async_client.post(
        "/api/v1/channels/manage/pairings",
        json={"channel": "telegram", "sender_id": sender_id},
    )
    assert create.status_code in (200, 201)
    created = create.json()
    assert created["channel"] == "telegram"
    assert created["sender_id"] == sender_id

    listed = (await async_client.get("/api/v1/channels/manage/pairings")).json()
    assert any(p.get("sender_id") == sender_id for p in listed)

    delete = await async_client.delete(f"/api/v1/channels/manage/pairings/{created['id']}")
    assert delete.status_code in (200, 204)
