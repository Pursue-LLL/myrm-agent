"""API integration tests for session handoff endpoint.

Tests POST /api/v1/chats/{chat_id}/handoff via ASGI transport.
Uses mock for channel_gateway since no real IM channels are available in test.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import httpx
import pytest
from httpx import ASGITransport

from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(preset="chats")
_GATEWAY_PATCH = "app.core.channel_bridge.channel_gateway"


@pytest.fixture
async def async_client() -> httpx.AsyncClient:
    async with httpx.AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
        headers={"Content-Type": "application/json"},
        timeout=60.0,
    ) as client:
        yield client


async def _create_chat(chat_id: str, source: str = "web") -> None:
    from app.database.models.chat import Chat
    from app.platform_utils import get_session_factory

    factory = get_session_factory()
    async with factory() as db:
        chat = Chat(
            id=chat_id,
            title=f"Test Chat {chat_id[:8]}",
            source=source,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        db.add(chat)
        await db.commit()


async def _create_pairing(channel: str, sender_id: str) -> None:
    from app.database.models.channel import ChannelPairingModel
    from app.platform_utils import get_session_factory

    factory = get_session_factory()
    async with factory() as db:
        pairing = ChannelPairingModel(
            id=uuid.uuid4().hex[:32],
            channel=channel,
            sender_id=sender_id,
            status="active",
        )
        db.add(pairing)
        await db.commit()


def _mock_channel(connected: bool = True) -> MagicMock:
    ch = MagicMock()
    ch.is_connected = connected
    return ch


@pytest.mark.asyncio
async def test_handoff_api_success(async_client: httpx.AsyncClient) -> None:
    chat_id = str(uuid.uuid4())
    await _create_chat(chat_id)
    await _create_pairing("telegram", "tg_api_user")

    with patch(_GATEWAY_PATCH) as mock_gw:
        mock_gw.bus.get_channel.return_value = _mock_channel()
        resp = await async_client.post(
            f"/api/v1/chats/{chat_id}/handoff",
            json={"target_channel": "telegram"},
        )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["targetChannel"] == "telegram"
    assert "tg_api_user" in data["targetSessionKey"]


@pytest.mark.asyncio
async def test_handoff_api_chat_not_found(async_client: httpx.AsyncClient) -> None:
    with patch(_GATEWAY_PATCH) as mock_gw:
        mock_gw.bus.get_channel.return_value = _mock_channel()
        resp = await async_client.post(
            f"/api/v1/chats/{uuid.uuid4()}/handoff",
            json={"target_channel": "telegram"},
        )

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_handoff_api_channel_not_connected(async_client: httpx.AsyncClient) -> None:
    chat_id = str(uuid.uuid4())
    await _create_chat(chat_id)

    with patch(_GATEWAY_PATCH) as mock_gw:
        mock_gw.bus.get_channel.return_value = _mock_channel(connected=False)
        resp = await async_client.post(
            f"/api/v1/chats/{chat_id}/handoff",
            json={"target_channel": "telegram"},
        )

    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_handoff_api_channel_not_found(async_client: httpx.AsyncClient) -> None:
    chat_id = str(uuid.uuid4())
    await _create_chat(chat_id)

    with patch(_GATEWAY_PATCH) as mock_gw:
        mock_gw.bus.get_channel.return_value = None
        resp = await async_client.post(
            f"/api/v1/chats/{chat_id}/handoff",
            json={"target_channel": "nonexistent"},
        )

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_handoff_api_same_channel(async_client: httpx.AsyncClient) -> None:
    chat_id = str(uuid.uuid4())
    await _create_chat(chat_id, source="telegram")

    from app.database.models.chat import Chat
    from app.platform_utils import get_session_factory

    factory = get_session_factory()
    async with factory() as db:
        from sqlalchemy import select

        chat = (await db.execute(select(Chat).where(Chat.id == chat_id))).scalar_one()
        chat.channel_session_key = "telegram:dm:some_user"
        await db.commit()

    with patch(_GATEWAY_PATCH) as mock_gw:
        mock_gw.bus.get_channel.return_value = _mock_channel()
        resp = await async_client.post(
            f"/api/v1/chats/{chat_id}/handoff",
            json={"target_channel": "telegram"},
        )

    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_handoff_api_no_pairing(async_client: httpx.AsyncClient) -> None:
    chat_id = str(uuid.uuid4())
    await _create_chat(chat_id)

    with patch(_GATEWAY_PATCH) as mock_gw:
        mock_gw.bus.get_channel.return_value = _mock_channel()
        resp = await async_client.post(
            f"/api/v1/chats/{chat_id}/handoff",
            json={"target_channel": "feishu"},
        )

    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_handoff_api_missing_body(async_client: httpx.AsyncClient) -> None:
    resp = await async_client.post(
        f"/api/v1/chats/{uuid.uuid4()}/handoff",
        json={},
    )
    assert resp.status_code == 422
