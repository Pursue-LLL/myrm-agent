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


@pytest.mark.asyncio
async def test_create_update_pairing_role_and_quota(async_client: httpx.AsyncClient) -> None:
    sender_id = f"user_{uuid.uuid4().hex[:8]}"
    create_res = await async_client.post(
        "/api/v1/channels/manage/pairings",
        json={
            "channel": "telegram",
            "sender_id": sender_id,
            "role": "admin",
            "daily_quota": 50,
        },
    )
    assert create_res.status_code in (200, 201)
    item = create_res.json()
    assert item["role"] == "admin"
    assert item["daily_quota"] == 50
    assert item["user_id"] == "sandbox"
    assert item["today_usage"] == 0
    pairing_id = item["id"]

    # Update role to member and daily_quota to 10
    update_res = await async_client.patch(
        f"/api/v1/channels/manage/pairings/{pairing_id}",
        json={
            "status": "active",
            "role": "member",
            "daily_quota": 10,
        },
    )
    assert update_res.status_code == 200
    updated = update_res.json()
    assert updated["role"] == "member"
    assert updated["daily_quota"] == 10
    assert updated["user_id"] == f"paired_member_telegram_{sender_id}"
    assert updated["today_usage"] == 0

    # Verify listing reflects updated role and quota
    listed = (await async_client.get("/api/v1/channels/manage/pairings")).json()
    target = next((p for p in listed if p["id"] == pairing_id), None)
    assert target is not None
    assert target["role"] == "member"
    assert target["daily_quota"] == 10
    assert target["user_id"] == f"paired_member_telegram_{sender_id}"
    assert target["today_usage"] == 0

    # Cleanup
    del_res = await async_client.delete(f"/api/v1/channels/manage/pairings/{pairing_id}")
    assert del_res.status_code in (200, 204)

