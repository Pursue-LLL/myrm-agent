"""PATCH /chats/{id}/active-moa-preset persists session MoA selection."""

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
async def test_patch_active_moa_preset_persists_and_get_returns_it(
    async_client: httpx.AsyncClient,
) -> None:
    chat_id = f"test-moa-preset-{uuid.uuid4().hex[:8]}"

    from app.database.models.chat import Chat
    from app.platform_utils import get_session_factory

    session_factory = get_session_factory()
    async with session_factory() as db:
        db.add(
            Chat(
                id=chat_id,
                title="MoA preset probe",
                action_mode="agent",
                source="web",
            )
        )
        await db.commit()

    patch_res = await async_client.patch(
        f"/api/v1/chats/{chat_id}/active-moa-preset",
        json={"active_moa_preset_id": "review"},
    )
    assert patch_res.status_code == 200, patch_res.text

    get_res = await async_client.get(f"/api/v1/chats/{chat_id}")
    assert get_res.status_code == 200, get_res.text
    assert get_res.json()["data"]["chat"]["activeMoaPresetId"] == "review"

    meta = await ChatService.get_chat_metadata(chat_id)
    assert meta is not None
    assert meta.active_moa_preset_id == "review"


@pytest.mark.asyncio
async def test_patch_active_moa_preset_rejects_invalid_id(
    async_client: httpx.AsyncClient,
) -> None:
    chat_id = f"test-moa-invalid-{uuid.uuid4().hex[:8]}"

    from app.database.models.chat import Chat
    from app.platform_utils import get_session_factory

    session_factory = get_session_factory()
    async with session_factory() as db:
        db.add(
            Chat(
                id=chat_id,
                title="MoA invalid preset",
                action_mode="agent",
                source="web",
            )
        )
        await db.commit()

    patch_res = await async_client.patch(
        f"/api/v1/chats/{chat_id}/active-moa-preset",
        json={"active_moa_preset_id": "not-a-preset"},
    )
    assert patch_res.status_code == 422 or patch_res.status_code == 400
