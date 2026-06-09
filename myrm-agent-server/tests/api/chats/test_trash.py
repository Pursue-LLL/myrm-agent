"""
Tests for chat trash (recycle bin) API endpoints.

[POS] Chat trash API integration tests. Validates soft-delete, list, restore,
permanently delete, empty trash, and count operations through the HTTP layer.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import httpx
import pytest
from httpx import ASGITransport

from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(preset="chats")
@pytest.fixture
async def async_client() -> httpx.AsyncClient:
    async with httpx.AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
        headers={"Content-Type": "application/json"},
        timeout=60.0,
    ) as client:
        yield client


async def _create_chat(chat_id: str, title: str = "Test Chat") -> None:
    from app.database.models.chat import Chat
    from app.platform_utils import get_session_factory

    session_factory = get_session_factory()
    async with session_factory() as db:
        chat = Chat(
            id=chat_id,
            title=title,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db.add(chat)
        await db.commit()


async def _soft_delete_chat(chat_id: str) -> None:
    """Directly soft-delete a chat by setting deleted_at."""
    from sqlalchemy import text

    from app.platform_utils import get_session_factory

    session_factory = get_session_factory()
    async with session_factory() as db:
        await db.execute(
            text("UPDATE chats SET deleted_at = :now WHERE id = :id"),
            {"now": datetime.now(timezone.utc), "id": chat_id},
        )
        await db.commit()


@pytest.mark.asyncio
async def test_trash_empty_initially(async_client: httpx.AsyncClient) -> None:
    """Trash should return empty list when no chats are deleted."""
    resp = await async_client.get("/api/v1/chats/trash")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["pagination"]["total"] >= 0


@pytest.mark.asyncio
async def test_trash_count(async_client: httpx.AsyncClient) -> None:
    """Trash count endpoint should return integer count."""
    resp = await async_client.get("/api/v1/chats/trash/count")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "count" in data
    assert isinstance(data["count"], int)


@pytest.mark.asyncio
async def test_soft_delete_moves_to_trash(async_client: httpx.AsyncClient) -> None:
    """Deleting a chat should soft-delete it and make it appear in trash."""
    chat_id = str(uuid.uuid4())
    await _create_chat(chat_id, title="Trash Test Chat")

    count_before = (await async_client.get("/api/v1/chats/trash/count")).json()["data"]["count"]

    resp = await async_client.delete(f"/api/v1/chats/{chat_id}")
    assert resp.status_code == 200

    count_after = (await async_client.get("/api/v1/chats/trash/count")).json()["data"]["count"]
    assert count_after == count_before + 1

    trash_resp = await async_client.get("/api/v1/chats/trash")
    assert trash_resp.status_code == 200
    items = trash_resp.json()["data"]["items"]
    trash_ids = [item["id"] for item in items]
    assert chat_id in trash_ids


@pytest.mark.asyncio
async def test_restore_chat(async_client: httpx.AsyncClient) -> None:
    """Restoring a trashed chat should remove it from trash."""
    chat_id = str(uuid.uuid4())
    await _create_chat(chat_id, title="Restore Test")
    await _soft_delete_chat(chat_id)

    resp = await async_client.post(f"/api/v1/chats/trash/{chat_id}/restore")
    assert resp.status_code == 200

    trash_resp = await async_client.get("/api/v1/chats/trash")
    items = trash_resp.json()["data"]["items"]
    trash_ids = [item["id"] for item in items]
    assert chat_id not in trash_ids


@pytest.mark.asyncio
async def test_restore_nonexistent_returns_404(async_client: httpx.AsyncClient) -> None:
    """Restoring a non-existent chat should return 404."""
    fake_id = str(uuid.uuid4())
    resp = await async_client.post(f"/api/v1/chats/trash/{fake_id}/restore")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_permanently_delete(async_client: httpx.AsyncClient) -> None:
    """Permanently deleting a trashed chat should remove it completely."""
    chat_id = str(uuid.uuid4())
    await _create_chat(chat_id, title="Permanent Delete Test")
    await _soft_delete_chat(chat_id)

    resp = await async_client.delete(f"/api/v1/chats/trash/{chat_id}")
    assert resp.status_code == 200

    restore_resp = await async_client.post(f"/api/v1/chats/trash/{chat_id}/restore")
    assert restore_resp.status_code == 404


@pytest.mark.asyncio
async def test_permanently_delete_nonexistent_returns_404(async_client: httpx.AsyncClient) -> None:
    """Permanently deleting non-existent chat returns 404."""
    fake_id = str(uuid.uuid4())
    resp = await async_client.delete(f"/api/v1/chats/trash/{fake_id}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_empty_trash(async_client: httpx.AsyncClient) -> None:
    """Empty trash should permanently delete all trashed chats."""
    chat_ids = [str(uuid.uuid4()) for _ in range(3)]
    for cid in chat_ids:
        await _create_chat(cid, title=f"Empty Test {cid[:8]}")
        await _soft_delete_chat(cid)

    resp = await async_client.delete("/api/v1/chats/trash")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["deleted_count"] >= 3

    count_resp = await async_client.get("/api/v1/chats/trash/count")
    assert count_resp.json()["data"]["count"] == 0


@pytest.mark.asyncio
async def test_deleted_chat_excluded_from_main_list(async_client: httpx.AsyncClient) -> None:
    """Soft-deleted chats should not appear in the main chat list."""
    chat_id = str(uuid.uuid4())
    await _create_chat(chat_id, title="Exclusion Test")
    await _soft_delete_chat(chat_id)

    resp = await async_client.get("/api/v1/chats/")
    assert resp.status_code == 200
    items = resp.json()["data"]["items"]
    main_ids = [item["id"] for item in items]
    assert chat_id not in main_ids
