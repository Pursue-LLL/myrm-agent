"""API integration tests for POST /api/v1/chats/{chat_id}/rewind."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from httpx import ASGITransport

from app.services.chat.session_continuity_service import ContinuitySyncError
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
        db.add(
            Chat(
                id=chat_id,
                title=f"Rewind Test {chat_id[:8]}",
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
        )
        await db.commit()


async def _insert_messages(chat_id: str) -> dict[str, str]:
    from app.database.models.chat import Message
    from app.platform_utils import get_session_factory

    factory = get_session_factory()
    base_time = datetime.now(UTC) - timedelta(minutes=4)
    ids = {
        "u1": str(uuid.uuid4()),
        "a1": str(uuid.uuid4()),
        "u2": str(uuid.uuid4()),
        "a2": str(uuid.uuid4()),
    }
    contents = {
        "u1": "First question",
        "a1": "First answer",
        "u2": "Second question",
        "a2": "Second answer",
    }
    async with factory() as db:
        for index, key in enumerate(["u1", "a1", "u2", "a2"]):
            role = "user" if key.startswith("u") else "assistant"
            ts = base_time + timedelta(seconds=index * 10)
            db.add(
                Message(
                    id=ids[key],
                    chat_id=chat_id,
                    role=role,
                    content=contents[key],
                    sent_at=ts,
                    sent_timezone="UTC",
                    created_at=ts,
                )
            )
        await db.commit()
    return ids


@pytest.mark.asyncio
async def test_rewind_user_message_returns_composer_text(
    async_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chat_id = f"rewind-{uuid.uuid4().hex[:8]}"
    await _create_chat(chat_id)
    ids = await _insert_messages(chat_id)

    async def _fake_sync(_chat_id: str) -> int:
        return 2

    monkeypatch.setattr(
        "app.services.chat.session_continuity_service.sync_chat_checkpoint_from_db",
        _fake_sync,
    )

    response = await async_client.post(
        f"/api/v1/chats/{chat_id}/rewind",
        json={"message_id": ids["u2"]},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    data = body["data"]
    assert data["composer_text"] == "Second question"
    assert data["deleted_count"] == 2
    assert data["message_index"] == 2


@pytest.mark.asyncio
async def test_rewind_rejects_assistant_message(async_client: httpx.AsyncClient) -> None:
    chat_id = f"rewind-assist-{uuid.uuid4().hex[:8]}"
    await _create_chat(chat_id)
    ids = await _insert_messages(chat_id)

    response = await async_client.post(
        f"/api/v1/chats/{chat_id}/rewind",
        json={"message_id": ids["a2"]},
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_truncate_after_calls_checkpoint_sync(
    async_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chat_id = f"rewind-trunc-{uuid.uuid4().hex[:8]}"
    await _create_chat(chat_id)
    ids = await _insert_messages(chat_id)
    synced: list[str] = []

    async def _fake_sync(target_chat_id: str) -> int:
        synced.append(target_chat_id)
        return 2

    monkeypatch.setattr(
        "app.services.chat.session_continuity_service.sync_chat_checkpoint_from_db",
        _fake_sync,
    )

    response = await async_client.post(
        f"/api/v1/chats/{chat_id}/truncate-after",
        json={"message_id": ids["u2"]},
    )
    assert response.status_code == 200
    assert synced == [chat_id]


@pytest.mark.asyncio
async def test_truncate_after_propagates_checkpoint_sync_error(
    async_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chat_id = f"rewind-sync-fail-{uuid.uuid4().hex[:8]}"
    await _create_chat(chat_id)
    ids = await _insert_messages(chat_id)

    async def _raise_sync(_chat_id: str) -> int:
        raise ContinuitySyncError("Synced 0/2 checkpoint threads for chat test-chat")

    monkeypatch.setattr(
        "app.services.chat.chat_turn._ChatTurnMixin._sync_checkpoint_after_mutation",
        _raise_sync,
    )

    response = await async_client.post(
        f"/api/v1/chats/{chat_id}/truncate-after",
        json={"message_id": ids["u2"]},
    )
    assert response.status_code == 500


@pytest.mark.asyncio
async def test_rewind_does_not_pause_goal_when_message_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services.chat.chat_service import ChatService

    chat_id = f"rewind-no-pause-{uuid.uuid4().hex[:8]}"
    await _create_chat(chat_id)

    pause_calls: list[str] = []

    async def _fake_pause(target_chat_id: str) -> bool:
        pause_calls.append(target_chat_id)
        return True

    monkeypatch.setattr(
        "app.services.chat.session_continuity_service.pause_active_goal_for_rewind",
        _fake_pause,
    )

    result = await ChatService.rewind_to_message(chat_id, str(uuid.uuid4()))
    assert result.success is False
    assert result.error == "MESSAGE_NOT_FOUND"
    assert pause_calls == []
