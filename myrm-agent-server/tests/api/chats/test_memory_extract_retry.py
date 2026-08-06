"""API tests for chat memory extract retry."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

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


async def _create_chat(chat_id: str, *, is_incognito: bool = False) -> None:
    from app.database.models.chat import Chat
    from app.platform_utils import get_session_factory

    session_factory = get_session_factory()
    async with session_factory() as db:
        db.add(
            Chat(
                id=chat_id,
                title=f"Test Chat {chat_id[:8]}",
                is_incognito=is_incognito,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
        )
        await db.commit()


@pytest.mark.asyncio
async def test_retry_extract_rejects_incognito_chat(
    async_client: httpx.AsyncClient,
) -> None:
    chat_id = "chat-retry-incognito"
    await _create_chat(chat_id, is_incognito=True)

    response = await async_client.post(f"/api/v1/chats/{chat_id}/memory/retry-extract")

    assert response.status_code == 400
    assert "Incognito" in str(response.json())


@pytest.mark.asyncio
async def test_retry_extract_returns_400_when_no_assistant_reply(
    async_client: httpx.AsyncClient,
) -> None:
    chat_id = "chat-retry-no-assistant"
    await _create_chat(chat_id, is_incognito=False)

    with patch(
        "app.api.chats.chat.memory_extract.schedule_retry_chat_memory_extract",
        new=AsyncMock(
            side_effect=ValueError("No assistant reply found for memory retry")
        ),
    ):
        response = await async_client.post(
            f"/api/v1/chats/{chat_id}/memory/retry-extract"
        )

    assert response.status_code == 400
    assert "No assistant reply" in str(response.json())


@pytest.mark.asyncio
async def test_retry_extract_schedules_for_normal_chat(
    async_client: httpx.AsyncClient,
) -> None:
    chat_id = "chat-retry-normal"
    await _create_chat(chat_id, is_incognito=False)

    with patch(
        "app.api.chats.chat.memory_extract.schedule_retry_chat_memory_extract",
        new=AsyncMock(return_value="scheduled"),
    ) as schedule_mock:
        response = await async_client.post(
            f"/api/v1/chats/{chat_id}/memory/retry-extract"
        )

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "scheduled"
    schedule_mock.assert_awaited_once_with(chat_id)
