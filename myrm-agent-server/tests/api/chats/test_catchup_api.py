"""Catchup API: briefs, the running status, and marking chats as read.

A chat is running exactly while the gateway has a turn in flight for it. The status comes
from the live execution registry, so it holds for every turn regardless of whether the
client that started it is still connected.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import datetime, timezone

import httpx
import pytest
from httpx import ASGITransport

from app.database.models.chat import Chat, Message
from app.platform_utils import get_session_factory
from app.services.agent.gateway import get_agent_gateway
from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(preset="chats")


@pytest.fixture
async def async_client() -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
        timeout=60.0,
    ) as client:
        yield client


async def _create_chat(*, with_assistant_reply: bool) -> str:
    chat_id = f"catchup-{uuid.uuid4().hex[:10]}"
    now = datetime.now(timezone.utc)
    async with get_session_factory()() as db:
        db.add(Chat(id=chat_id, title="Catchup status", action_mode="fast", source="web", created_at=now, updated_at=now))
        if with_assistant_reply:
            db.add(
                Message(
                    id=f"msg-{uuid.uuid4().hex[:10]}",
                    chat_id=chat_id,
                    role="assistant",
                    content="The report is ready.",
                    sent_at=now,
                    sent_timezone="UTC",
                )
            )
        await db.commit()
    return chat_id


async def _brief_status(client: httpx.AsyncClient, chat_id: str) -> str | None:
    response = await client.get("/api/v1/chats/catchup")
    assert response.status_code == 200
    briefs = response.json()["data"]["briefs"]
    return next((brief["status"] for brief in briefs if brief["chat_id"] == chat_id), None)


@pytest.mark.asyncio
async def test_a_chat_with_a_turn_in_flight_is_running(async_client: httpx.AsyncClient) -> None:
    chat_id = await _create_chat(with_assistant_reply=False)
    gateway = get_agent_gateway()
    gateway.reserve_session(chat_id, active_message_id="msg-running")
    try:
        assert await _brief_status(async_client, chat_id) == "running"
    finally:
        gateway.release_session(chat_id)


@pytest.mark.asyncio
async def test_a_chat_without_a_turn_in_flight_is_completed(async_client: httpx.AsyncClient) -> None:
    chat_id = await _create_chat(with_assistant_reply=True)

    assert await _brief_status(async_client, chat_id) == "completed"


@pytest.mark.asyncio
async def test_a_chat_stops_being_running_once_its_turn_is_released(async_client: httpx.AsyncClient) -> None:
    chat_id = await _create_chat(with_assistant_reply=True)
    gateway = get_agent_gateway()
    gateway.reserve_session(chat_id, active_message_id="msg-running")
    try:
        assert await _brief_status(async_client, chat_id) == "running"
    finally:
        gateway.release_session(chat_id)

    assert await _brief_status(async_client, chat_id) == "completed"


@pytest.mark.asyncio
async def test_a_chat_marked_as_read_leaves_the_briefs(async_client: httpx.AsyncClient) -> None:
    chat_id = await _create_chat(with_assistant_reply=True)
    assert await _brief_status(async_client, chat_id) == "completed"

    response = await async_client.post(f"/api/v1/chats/{chat_id}/read")

    assert response.status_code == 200
    assert await _brief_status(async_client, chat_id) is None


@pytest.mark.asyncio
async def test_marking_an_unknown_chat_as_read_answers_not_found(async_client: httpx.AsyncClient) -> None:
    response = await async_client.post(f"/api/v1/chats/missing-{uuid.uuid4().hex[:10]}/read")

    assert response.status_code == 404
