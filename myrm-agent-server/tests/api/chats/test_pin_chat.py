"""
Tests for chat pin/unpin/reorder API endpoints.

[POS] Pinned chats API integration tests. Validates pin, unpin, reorder,
max-pin limit, and idempotent operations through the HTTP layer.
"""

from __future__ import annotations

import uuid

import httpx
import pytest
from httpx import ASGITransport

from app.main import app


async def _unpin_all(async_client: httpx.AsyncClient) -> None:
    """Unpin all currently pinned chats to avoid cross-test pin limit conflicts."""
    resp = await async_client.get("/api/v1/chats/", params={"page": 1, "page_size": 100})
    if resp.status_code != 200:
        return
    for item in resp.json().get("data", {}).get("items", []):
        if item.get("isPinned"):
            await async_client.patch(f"/api/v1/chats/{item['id']}/unpin")


@pytest.fixture
async def async_client() -> httpx.AsyncClient:
    async with httpx.AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
        headers={"Content-Type": "application/json"},
        timeout=60.0,
    ) as client:
        yield client


@pytest.fixture(autouse=True)
async def _cleanup_pinned_chats_before_test(async_client: httpx.AsyncClient) -> None:
    """Shared test DB retains pin state; reset so MAX_PINNED limit tests stay isolated."""
    await _unpin_all(async_client)


async def _create_chat(chat_id: str) -> None:
    from datetime import datetime, timezone

    from app.database.models.chat import Chat
    from app.platform_utils import get_session_factory

    session_factory = get_session_factory()
    async with session_factory() as db:
        chat = Chat(
            id=chat_id,
            title=f"Test Chat {chat_id[:8]}",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db.add(chat)
        await db.commit()


@pytest.mark.asyncio
async def test_pin_chat(async_client: httpx.AsyncClient) -> None:
    chat_id = str(uuid.uuid4())
    await _create_chat(chat_id)

    resp = await async_client.patch(f"/api/v1/chats/{chat_id}/pin")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["isPinned"] is True
    assert data["pinOrder"] >= 1


@pytest.mark.asyncio
async def test_pin_already_pinned_is_idempotent(async_client: httpx.AsyncClient) -> None:
    chat_id = str(uuid.uuid4())
    await _create_chat(chat_id)

    await async_client.patch(f"/api/v1/chats/{chat_id}/pin")
    resp = await async_client.patch(f"/api/v1/chats/{chat_id}/pin")
    assert resp.status_code == 200
    assert resp.json()["data"]["isPinned"] is True


@pytest.mark.asyncio
async def test_unpin_chat(async_client: httpx.AsyncClient) -> None:
    chat_id = str(uuid.uuid4())
    await _create_chat(chat_id)

    await async_client.patch(f"/api/v1/chats/{chat_id}/pin")
    resp = await async_client.patch(f"/api/v1/chats/{chat_id}/unpin")
    assert resp.status_code == 200
    assert resp.json()["data"]["isPinned"] is False
    assert resp.json()["data"]["pinOrder"] == 0


@pytest.mark.asyncio
async def test_pin_nonexistent_chat_returns_404(async_client: httpx.AsyncClient) -> None:
    fake_id = str(uuid.uuid4())
    resp = await async_client.patch(f"/api/v1/chats/{fake_id}/pin")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_unpin_nonexistent_chat_returns_404(async_client: httpx.AsyncClient) -> None:
    fake_id = str(uuid.uuid4())
    resp = await async_client.patch(f"/api/v1/chats/{fake_id}/unpin")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_reorder_pinned_chats(async_client: httpx.AsyncClient) -> None:
    ids = [str(uuid.uuid4()) for _ in range(3)]
    for cid in ids:
        await _create_chat(cid)
        await async_client.patch(f"/api/v1/chats/{cid}/pin")

    reorder_payload = {
        "items": [
            {"id": ids[2], "pin_order": 1},
            {"id": ids[0], "pin_order": 2},
            {"id": ids[1], "pin_order": 3},
        ]
    }
    resp = await async_client.put("/api/v1/chats/pin-reorder", json=reorder_payload)
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_max_pinned_limit(async_client: httpx.AsyncClient) -> None:
    ids = [str(uuid.uuid4()) for _ in range(10)]
    for cid in ids:
        await _create_chat(cid)

    for cid in ids[:9]:
        resp = await async_client.patch(f"/api/v1/chats/{cid}/pin")
        assert resp.status_code == 200

    resp = await async_client.patch(f"/api/v1/chats/{ids[9]}/pin")
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_unpin_already_unpinned_chat(async_client: httpx.AsyncClient) -> None:
    """Unpin a chat that was never pinned — should succeed silently."""
    chat_id = str(uuid.uuid4())
    await _create_chat(chat_id)

    resp = await async_client.patch(f"/api/v1/chats/{chat_id}/unpin")
    assert resp.status_code == 200
    assert resp.json()["data"]["isPinned"] is False


@pytest.mark.asyncio
async def test_pin_unpin_repin_lifecycle(async_client: httpx.AsyncClient) -> None:
    """Full lifecycle: pin -> unpin -> re-pin should assign a new pinOrder."""
    chat_id = str(uuid.uuid4())
    await _create_chat(chat_id)

    r1 = await async_client.patch(f"/api/v1/chats/{chat_id}/pin")
    assert r1.status_code == 200
    first_order = r1.json()["data"]["pinOrder"]

    await async_client.patch(f"/api/v1/chats/{chat_id}/unpin")

    r2 = await async_client.patch(f"/api/v1/chats/{chat_id}/pin")
    assert r2.status_code == 200
    assert r2.json()["data"]["isPinned"] is True
    assert r2.json()["data"]["pinOrder"] >= first_order


@pytest.mark.asyncio
async def test_reorder_verifies_new_order_in_list(async_client: httpx.AsyncClient) -> None:
    """Reorder then fetch list to verify pinOrder is persisted correctly."""
    await _unpin_all(async_client)

    ids = [str(uuid.uuid4()) for _ in range(3)]
    for cid in ids:
        await _create_chat(cid)
        await async_client.patch(f"/api/v1/chats/{cid}/pin")

    reorder_payload = {
        "items": [
            {"id": ids[2], "pin_order": 1},
            {"id": ids[0], "pin_order": 2},
            {"id": ids[1], "pin_order": 3},
        ]
    }
    await async_client.put("/api/v1/chats/pin-reorder", json=reorder_payload)

    resp = await async_client.get("/api/v1/chats/", params={"page": 1, "page_size": 50})
    assert resp.status_code == 200
    items_by_id = {it["id"]: it for it in resp.json()["data"]["items"]}
    assert items_by_id[ids[2]]["pinOrder"] == 1
    assert items_by_id[ids[0]]["pinOrder"] == 2
    assert items_by_id[ids[1]]["pinOrder"] == 3


@pytest.mark.asyncio
async def test_reorder_invalid_pin_order_zero(async_client: httpx.AsyncClient) -> None:
    """pin_order must be >= 1; zero should be rejected by Pydantic validation."""
    payload = {"items": [{"id": str(uuid.uuid4()), "pin_order": 0}]}
    resp = await async_client.put("/api/v1/chats/pin-reorder", json=payload)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_reorder_exceeds_max_items(async_client: httpx.AsyncClient) -> None:
    """Sending more than MAX_PINNED_CHATS items should be rejected."""
    items = [{"id": str(uuid.uuid4()), "pin_order": i + 1} for i in range(10)]
    resp = await async_client.put("/api/v1/chats/pin-reorder", json={"items": items})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_pin_reflected_in_chat_list(async_client: httpx.AsyncClient) -> None:
    """After pinning, the chat list should show isPinned=True."""
    chat_id = str(uuid.uuid4())
    await _create_chat(chat_id)
    await async_client.patch(f"/api/v1/chats/{chat_id}/pin")

    resp = await async_client.get("/api/v1/chats/", params={"page": 1, "page_size": 50})
    assert resp.status_code == 200
    found = [it for it in resp.json()["data"]["items"] if it["id"] == chat_id]
    assert len(found) == 1
    assert found[0]["isPinned"] is True
    assert found[0]["pinOrder"] >= 1
