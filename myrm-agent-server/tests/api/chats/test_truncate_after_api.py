"""API integration tests for POST /api/v1/chats/{chat_id}/truncate-after.

Full-chain test: create chat → insert messages via ORM → call truncate-after
endpoint → verify DB state through API and direct ORM query.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

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


async def _create_chat(chat_id: str) -> None:
    from app.database.models.chat import Chat
    from app.platform_utils import get_session_factory

    factory = get_session_factory()
    async with factory() as db:
        chat = Chat(
            id=chat_id,
            title=f"Truncate Test {chat_id[:8]}",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        db.add(chat)
        await db.commit()


async def _insert_messages(chat_id: str, count: int) -> list[str]:
    """Insert *count* messages with ascending timestamps. Returns message IDs."""
    from app.database.models.chat import Message
    from app.platform_utils import get_session_factory

    factory = get_session_factory()
    base_time = datetime.now(UTC) - timedelta(minutes=count)
    ids: list[str] = []
    async with factory() as db:
        for i in range(count):
            msg_id = str(uuid.uuid4())
            ids.append(msg_id)
            role = "user" if i % 2 == 0 else "assistant"
            ts = base_time + timedelta(seconds=i * 10)
            msg = Message(
                id=msg_id,
                chat_id=chat_id,
                role=role,
                content=f"Message {i}",
                sent_at=ts,
                sent_timezone="UTC",
                created_at=ts,
            )
            db.add(msg)
        await db.commit()
    return ids


async def _count_active_messages(chat_id: str) -> int:
    from sqlalchemy import func, select

    from app.database.models.chat import Message
    from app.platform_utils import get_session_factory

    factory = get_session_factory()
    async with factory() as db:
        result = await db.execute(
            select(func.count()).where(Message.chat_id == chat_id, Message.is_active.is_(True))
        )
        return result.scalar_one()


@pytest.mark.asyncio
async def test_truncate_after_deletes_target_and_subsequent(
    async_client: httpx.AsyncClient,
) -> None:
    """Truncating at msg[2] should delete msg[2..4], leaving msg[0..1]."""
    chat_id = str(uuid.uuid4())
    await _create_chat(chat_id)
    ids = await _insert_messages(chat_id, 5)

    resp = await async_client.post(
        f"/api/v1/chats/{chat_id}/truncate-after",
        json={"message_id": ids[2]},
    )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["success"] is True
    assert data["deleted_count"] == 3

    remaining = await _count_active_messages(chat_id)
    assert remaining == 2


@pytest.mark.asyncio
async def test_truncate_after_nonexistent_chat(
    async_client: httpx.AsyncClient,
) -> None:
    resp = await async_client.post(
        f"/api/v1/chats/{uuid.uuid4()}/truncate-after",
        json={"message_id": str(uuid.uuid4())},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_truncate_after_nonexistent_message(
    async_client: httpx.AsyncClient,
) -> None:
    chat_id = str(uuid.uuid4())
    await _create_chat(chat_id)
    await _insert_messages(chat_id, 3)

    resp = await async_client.post(
        f"/api/v1/chats/{chat_id}/truncate-after",
        json={"message_id": str(uuid.uuid4())},
    )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["success"] is False
    assert data["deleted_count"] == 0


@pytest.mark.asyncio
async def test_truncate_after_first_message_clears_all(
    async_client: httpx.AsyncClient,
) -> None:
    """Truncating from the very first message should remove everything."""
    chat_id = str(uuid.uuid4())
    await _create_chat(chat_id)
    ids = await _insert_messages(chat_id, 4)

    resp = await async_client.post(
        f"/api/v1/chats/{chat_id}/truncate-after",
        json={"message_id": ids[0]},
    )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["success"] is True
    assert data["deleted_count"] == 4

    remaining = await _count_active_messages(chat_id)
    assert remaining == 0


@pytest.mark.asyncio
async def test_truncate_after_last_message(
    async_client: httpx.AsyncClient,
) -> None:
    """Truncating the last message should delete only that one."""
    chat_id = str(uuid.uuid4())
    await _create_chat(chat_id)
    ids = await _insert_messages(chat_id, 3)

    resp = await async_client.post(
        f"/api/v1/chats/{chat_id}/truncate-after",
        json={"message_id": ids[-1]},
    )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["success"] is True
    assert data["deleted_count"] == 1

    remaining = await _count_active_messages(chat_id)
    assert remaining == 2


@pytest.mark.asyncio
async def test_truncate_after_missing_body(
    async_client: httpx.AsyncClient,
) -> None:
    """Missing message_id in request body should return 422."""
    resp = await async_client.post(
        f"/api/v1/chats/{uuid.uuid4()}/truncate-after",
        json={},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_truncate_after_updates_last_message(
    async_client: httpx.AsyncClient,
) -> None:
    """After truncating, the chat's last_message field should reflect the new latest message."""
    chat_id = str(uuid.uuid4())
    await _create_chat(chat_id)
    ids = await _insert_messages(chat_id, 4)

    await async_client.post(
        f"/api/v1/chats/{chat_id}/truncate-after",
        json={"message_id": ids[2]},
    )

    from sqlalchemy import select

    from app.database.models.chat import Chat
    from app.platform_utils import get_session_factory

    factory = get_session_factory()
    async with factory() as db:
        chat = (await db.execute(select(Chat).where(Chat.id == chat_id))).scalar_one()
        assert chat.last_message is not None
        assert "Message 1" in chat.last_message


@pytest.mark.asyncio
async def test_truncate_after_empty_chat(
    async_client: httpx.AsyncClient,
) -> None:
    """Truncating on a chat with zero messages returns success=false."""
    chat_id = str(uuid.uuid4())
    await _create_chat(chat_id)

    resp = await async_client.post(
        f"/api/v1/chats/{chat_id}/truncate-after",
        json={"message_id": str(uuid.uuid4())},
    )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["success"] is False


@pytest.mark.asyncio
async def test_truncate_after_idempotent(
    async_client: httpx.AsyncClient,
) -> None:
    """Calling truncate twice for the same message: second call returns failure."""
    chat_id = str(uuid.uuid4())
    await _create_chat(chat_id)
    ids = await _insert_messages(chat_id, 3)

    resp1 = await async_client.post(
        f"/api/v1/chats/{chat_id}/truncate-after",
        json={"message_id": ids[1]},
    )
    assert resp1.json()["data"]["success"] is True
    assert resp1.json()["data"]["deleted_count"] == 2

    resp2 = await async_client.post(
        f"/api/v1/chats/{chat_id}/truncate-after",
        json={"message_id": ids[1]},
    )
    assert resp2.json()["data"]["success"] is False
    assert resp2.json()["data"]["deleted_count"] == 0


@pytest.mark.asyncio
async def test_truncate_after_single_message(
    async_client: httpx.AsyncClient,
) -> None:
    """Chat with a single message: truncating it leaves no messages."""
    chat_id = str(uuid.uuid4())
    await _create_chat(chat_id)
    ids = await _insert_messages(chat_id, 1)

    resp = await async_client.post(
        f"/api/v1/chats/{chat_id}/truncate-after",
        json={"message_id": ids[0]},
    )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["success"] is True
    assert data["deleted_count"] == 1

    remaining = await _count_active_messages(chat_id)
    assert remaining == 0


@pytest.mark.asyncio
async def test_truncate_isolation_between_chats(
    async_client: httpx.AsyncClient,
) -> None:
    """Truncating one chat does not affect messages in another chat."""
    chat_a = str(uuid.uuid4())
    chat_b = str(uuid.uuid4())
    await _create_chat(chat_a)
    await _create_chat(chat_b)
    ids_a = await _insert_messages(chat_a, 3)
    await _insert_messages(chat_b, 3)

    resp = await async_client.post(
        f"/api/v1/chats/{chat_a}/truncate-after",
        json={"message_id": ids_a[0]},
    )

    assert resp.json()["data"]["deleted_count"] == 3

    remaining_b = await _count_active_messages(chat_b)
    assert remaining_b == 3
