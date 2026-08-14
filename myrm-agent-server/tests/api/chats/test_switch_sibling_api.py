"""API integration tests for POST /api/v1/chats/{chat_id}/switch-sibling.

Covers the endpoint wiring: chat existence check, service call with chat_id,
and the not-found branches. The sibling DB mechanics live in the repository
layer and are covered by the service-level mutation usage tests.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
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


async def _create_chat(chat_id: str) -> None:
    from app.database.models.chat import Chat
    from app.platform_utils import get_session_factory

    factory = get_session_factory()
    async with factory() as db:
        chat = Chat(
            id=chat_id,
            title=f"Switch Sibling Test {chat_id[:8]}",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        db.add(chat)
        await db.commit()


def _payload() -> dict[str, str]:
    return {
        "sibling_group_id": str(uuid.uuid4()),
        "target_message_id": str(uuid.uuid4()),
    }


@pytest.mark.asyncio
async def test_switch_sibling_success(async_client: httpx.AsyncClient) -> None:
    chat_id = str(uuid.uuid4())
    await _create_chat(chat_id)
    with patch(
        "app.services.chat.chat_service.ChatService.switch_sibling",
        new_callable=AsyncMock,
        return_value=True,
    ):
        resp = await async_client.post(
            f"/api/v1/chats/{chat_id}/switch-sibling",
            json=_payload(),
        )
    assert resp.status_code == 200
    assert resp.json()["data"]["success"] is True


@pytest.mark.asyncio
async def test_switch_sibling_nonexistent_chat(async_client: httpx.AsyncClient) -> None:
    resp = await async_client.post(
        f"/api/v1/chats/{uuid.uuid4()}/switch-sibling",
        json=_payload(),
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_switch_sibling_target_not_found(async_client: httpx.AsyncClient) -> None:
    chat_id = str(uuid.uuid4())
    await _create_chat(chat_id)
    with patch(
        "app.services.chat.chat_service.ChatService.switch_sibling",
        new_callable=AsyncMock,
        return_value=False,
    ):
        resp = await async_client.post(
            f"/api/v1/chats/{chat_id}/switch-sibling",
            json=_payload(),
        )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_switch_sibling_missing_body(async_client: httpx.AsyncClient) -> None:
    resp = await async_client.post(
        f"/api/v1/chats/{uuid.uuid4()}/switch-sibling",
        json={},
    )
    assert resp.status_code == 422
