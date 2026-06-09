"""
Tests for batch-delete chat API endpoint.

[POS] Batch delete integration tests. Validates POST /chats/batch-delete through
the HTTP layer with real database operations (no mocks).
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


@pytest.mark.asyncio
async def test_batch_delete_success(async_client: httpx.AsyncClient) -> None:
    """Batch deleting multiple chats should soft-delete all of them."""
    chat_ids = [str(uuid.uuid4()) for _ in range(3)]
    for cid in chat_ids:
        await _create_chat(cid, title=f"Batch Test {cid[:8]}")

    resp = await async_client.post(
        "/api/v1/chats/batch-delete",
        json={"ids": chat_ids},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["deleted"] == 3
    assert data["failed"] == 0

    main_resp = await async_client.get("/api/v1/chats/")
    main_ids = [item["id"] for item in main_resp.json()["data"]["items"]]
    for cid in chat_ids:
        assert cid not in main_ids

    trash_resp = await async_client.get("/api/v1/chats/trash")
    trash_ids = [item["id"] for item in trash_resp.json()["data"]["items"]]
    for cid in chat_ids:
        assert cid in trash_ids


@pytest.mark.asyncio
async def test_batch_delete_partial_failure(async_client: httpx.AsyncClient) -> None:
    """Batch delete with mix of valid and invalid IDs should report partial results."""
    valid_id = str(uuid.uuid4())
    fake_id = str(uuid.uuid4())
    await _create_chat(valid_id, title="Batch Partial Test")

    resp = await async_client.post(
        "/api/v1/chats/batch-delete",
        json={"ids": [valid_id, fake_id]},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["deleted"] == 1
    assert data["failed"] == 1


@pytest.mark.asyncio
async def test_batch_delete_empty_ids_rejected(async_client: httpx.AsyncClient) -> None:
    """Batch delete with empty IDs list should be rejected by validation."""
    resp = await async_client.post(
        "/api/v1/chats/batch-delete",
        json={"ids": []},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_batch_delete_exceeds_max_rejected(async_client: httpx.AsyncClient) -> None:
    """Batch delete with more than 50 IDs should be rejected by validation."""
    ids = [str(uuid.uuid4()) for _ in range(51)]
    resp = await async_client.post(
        "/api/v1/chats/batch-delete",
        json={"ids": ids},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_batch_delete_single_item(async_client: httpx.AsyncClient) -> None:
    """Batch delete with a single ID should work like regular delete."""
    chat_id = str(uuid.uuid4())
    await _create_chat(chat_id, title="Batch Single Test")

    resp = await async_client.post(
        "/api/v1/chats/batch-delete",
        json={"ids": [chat_id]},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["deleted"] == 1
    assert data["failed"] == 0
