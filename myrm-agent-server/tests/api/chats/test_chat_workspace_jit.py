"""GET /chats/{id} JIT-binds harness workspace_dir when DB value is unset."""

from __future__ import annotations

import uuid

import httpx
import pytest
from httpx import ASGITransport

from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(preset="chats")
from app.services.chat.chat_service import ChatService


@pytest.fixture
async def async_client() -> httpx.AsyncClient:
    async with httpx.AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
        headers={"Content-Type": "application/json"},
        timeout=60.0,
    ) as client:
        yield client


@pytest.mark.asyncio
async def test_get_chat_populates_workspace_dir_when_null(
    async_client: httpx.AsyncClient,
) -> None:
    """[evidence] Mirrors agent_params converter: chat_{{id}} sandbox path exposed to frontend."""
    chat_id = f"test-ws-jit-{uuid.uuid4().hex[:8]}"

    from app.database.models.chat import Chat
    from app.platform_utils import get_session_factory

    session_factory = get_session_factory()
    async with session_factory() as db:
        chat = Chat(
            id=chat_id,
            title="JIT workspace probe",
            action_mode="agent",
            source="web",
        )
        db.add(chat)
        await db.commit()

    res = await async_client.get(f"/api/v1/chats/{chat_id}")
    assert res.status_code == 200, res.text
    payload = res.json()
    ws = payload["data"]["chat"]["workspace_dir"]
    assert isinstance(ws, str) and len(ws) > 0

    meta = await ChatService.get_chat_metadata(chat_id)
    assert meta is not None
    assert meta.workspace_dir == ws


@pytest.mark.asyncio
async def test_get_chat_preserves_existing_workspace_dir(
    async_client: httpx.AsyncClient,
) -> None:
    """If DB already has workspace_dir, GET must not overwrite with a different string."""
    chat_id = f"test-ws-keep-{uuid.uuid4().hex[:8]}"
    existing = "/tmp/myrm_workspace_jit_should_not_exist_please"

    from app.database.models.chat import Chat
    from app.platform_utils import get_session_factory

    session_factory = get_session_factory()
    async with session_factory() as db:
        chat = Chat(
            id=chat_id,
            title="Keep workspace_dir",
            action_mode="agent",
            source="web",
            workspace_dir=existing,
        )
        db.add(chat)
        await db.commit()

    res = await async_client.get(f"/api/v1/chats/{chat_id}")
    assert res.status_code == 200, res.text
    assert res.json()["data"]["chat"]["workspace_dir"] == existing
