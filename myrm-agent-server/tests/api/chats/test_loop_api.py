"""API integration tests for session loop endpoints:
- POST /api/v1/chats/{chat_id}/loop/start
- POST /api/v1/chats/{chat_id}/loop/stop
- GET /api/v1/chats/{chat_id}/loop/status
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import httpx
import pytest
from httpx import ASGITransport

from app.services.loop import SessionLoopManager
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


async def _create_test_chat(chat_id: str) -> None:
    from app.database.models.chat import Chat
    from app.platform_utils import get_session_factory

    factory = get_session_factory()
    async with factory() as db:
        db.add(
            Chat(
                id=chat_id,
                title=f"Loop Test {chat_id[:8]}",
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
        )
        await db.commit()


@pytest.mark.asyncio
async def test_session_loop_api_lifecycle(async_client: httpx.AsyncClient) -> None:
    chat_id = f"test-loop-{uuid.uuid4().hex[:12]}"
    await _create_test_chat(chat_id)

    # 1. Check status before starting
    status_res = await async_client.get(f"/api/v1/chats/{chat_id}/loop/status")
    assert status_res.status_code == 200
    data = status_res.json()["data"]
    assert not data["is_active"]

    # 2. Start loop
    start_res = await async_client.post(
        f"/api/v1/chats/{chat_id}/loop/start",
        json={"command": "5m check cluster health --times 3"},
    )
    assert start_res.status_code == 200
    start_data = start_res.json()["data"]
    assert start_data["is_active"]
    assert start_data["prompt"] == "check cluster health"
    assert start_data["times_limit"] == 3

    # 3. Status after start
    status_active = await async_client.get(f"/api/v1/chats/{chat_id}/loop/status")
    assert status_active.status_code == 200
    active_data = status_active.json()["data"]
    assert active_data["is_active"]
    assert active_data["mode"] == "interval"

    # 4. Stop loop
    stop_res = await async_client.post(
        f"/api/v1/chats/{chat_id}/loop/stop",
        json={"reason": "user_stopped"},
    )
    assert stop_res.status_code == 200
    stop_data = stop_res.json()["data"]
    assert not stop_data["is_active"]

    # Clean up background tasks
    await SessionLoopManager.get_instance().stop_loop(chat_id)
