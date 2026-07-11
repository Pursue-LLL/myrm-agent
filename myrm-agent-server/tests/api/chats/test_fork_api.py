"""API integration tests for fork endpoint.

Tests POST /api/v1/chats/{chat_id}/fork via ASGI transport.
Covers: normal fork, -1 (last message) shorthand, validation errors.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import patch

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


async def _create_chat_with_messages(chat_id: str, message_count: int = 5) -> None:
    from app.database.models import Chat, Message
    from app.platform_utils import get_session_factory

    factory = get_session_factory()
    async with factory() as db:
        chat = Chat(
            id=chat_id,
            title=f"Test Chat {chat_id[:8]}",
            source="web",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        db.add(chat)
        now = datetime.now(UTC)
        for i in range(message_count):
            db.add(
                Message(
                    id=str(uuid.uuid4()),
                    chat_id=chat_id,
                    role="user" if i % 2 == 0 else "assistant",
                    content=f"Message {i}",
                    sent_at=now,
                    sent_timezone="UTC",
                )
            )
        await db.commit()


@pytest.mark.asyncio
async def test_fork_with_valid_index(async_client: httpx.AsyncClient) -> None:
    """Fork at explicit valid message_index succeeds."""
    chat_id = str(uuid.uuid4())
    await _create_chat_with_messages(chat_id, message_count=5)

    with patch("app.platform_utils.get_checkpointer", return_value=None):
        resp = await async_client.post(
            f"/api/v1/chats/{chat_id}/fork",
            json={"message_index": 2},
        )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["parent_chat_id"] == chat_id
    assert data["fork_point"] == 2
    assert data["new_chat_id"] is not None


@pytest.mark.asyncio
async def test_fork_with_minus_one_resolves_to_last(async_client: httpx.AsyncClient) -> None:
    """message_index=-1 resolves to last message index."""
    chat_id = str(uuid.uuid4())
    await _create_chat_with_messages(chat_id, message_count=8)

    with patch("app.platform_utils.get_checkpointer", return_value=None):
        resp = await async_client.post(
            f"/api/v1/chats/{chat_id}/fork",
            json={"message_index": -1},
        )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["fork_point"] == 7  # 8 messages, last index = 7
    assert data["new_chat_id"] is not None


@pytest.mark.asyncio
async def test_fork_minus_one_empty_chat_returns_400(async_client: httpx.AsyncClient) -> None:
    """message_index=-1 on empty chat returns validation error."""
    from app.database.models.chat import Chat
    from app.platform_utils import get_session_factory

    chat_id = str(uuid.uuid4())
    factory = get_session_factory()
    async with factory() as db:
        db.add(Chat(id=chat_id, title="Empty", created_at=datetime.now(UTC), updated_at=datetime.now(UTC)))
        await db.commit()

    with patch("app.platform_utils.get_checkpointer", return_value=None):
        resp = await async_client.post(
            f"/api/v1/chats/{chat_id}/fork",
            json={"message_index": -1},
        )

    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_fork_invalid_index_below_minus_one(async_client: httpx.AsyncClient) -> None:
    """message_index < -1 returns validation error."""
    chat_id = str(uuid.uuid4())
    await _create_chat_with_messages(chat_id, message_count=3)

    with patch("app.platform_utils.get_checkpointer", return_value=None):
        resp = await async_client.post(
            f"/api/v1/chats/{chat_id}/fork",
            json={"message_index": -2},
        )

    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_fork_index_out_of_range(async_client: httpx.AsyncClient) -> None:
    """message_index >= total messages returns error."""
    chat_id = str(uuid.uuid4())
    await _create_chat_with_messages(chat_id, message_count=3)

    with patch("app.platform_utils.get_checkpointer", return_value=None):
        resp = await async_client.post(
            f"/api/v1/chats/{chat_id}/fork",
            json={"message_index": 10},
        )

    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_fork_nonexistent_chat(async_client: httpx.AsyncClient) -> None:
    """Fork on non-existent chat returns 404."""
    with patch("app.platform_utils.get_checkpointer", return_value=None):
        resp = await async_client.post(
            f"/api/v1/chats/{uuid.uuid4()}/fork",
            json={"message_index": 0},
        )

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_fork_with_custom_title(async_client: httpx.AsyncClient) -> None:
    """Fork with custom new_title uses provided title."""
    chat_id = str(uuid.uuid4())
    await _create_chat_with_messages(chat_id, message_count=3)

    with patch("app.platform_utils.get_checkpointer", return_value=None):
        resp = await async_client.post(
            f"/api/v1/chats/{chat_id}/fork",
            json={"message_index": 1, "new_title": "My Custom Branch"},
        )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["new_chat_id"] is not None

    from app.database.models.chat import Chat
    from app.platform_utils import get_session_factory
    from sqlalchemy import select

    factory = get_session_factory()
    async with factory() as db:
        child = (await db.execute(select(Chat).where(Chat.id == data["new_chat_id"]))).scalar_one()
        assert child.title == "My Custom Branch"
