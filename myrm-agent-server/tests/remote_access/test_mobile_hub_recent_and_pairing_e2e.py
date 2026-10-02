"""Mobile Hub finished-task recovery: recent sessions listing and pairing relaxation.

[POS]
End-to-end coverage over a minimal app with a real DB (no gateway mocks):
finished (non-active) chats appear in ``recentSessions`` and can mint scoped
control tokens from the phone; trashed and missing chats stay rejected.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import httpx
import pytest
from httpx import ASGITransport

from app.remote_access.pairing import (
    MOBILE_HUB_CONTROL_PURPOSE,
    MOBILE_HUB_LIST_PURPOSE,
    create_pairing_token,
    parse_pairing_token,
)
from tests.support.minimal_app import build_minimal_app

app = build_minimal_app("remote_access", "chats")


@pytest.fixture
async def async_client() -> httpx.AsyncClient:
    async with httpx.AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
        headers={"Content-Type": "application/json"},
        timeout=60.0,
    ) as client:
        yield client


async def _create_chat(chat_id: str, title: str, agent_id: str | None = None) -> None:
    from app.database.models.chat import Chat
    from app.platform_utils import get_session_factory

    now = datetime.now(timezone.utc)
    session_factory = get_session_factory()
    async with session_factory() as db:
        db.add(Chat(id=chat_id, title=title, agent_id=agent_id, created_at=now, updated_at=now))
        await db.commit()


async def _soft_delete_chat(chat_id: str) -> None:
    from sqlalchemy import text

    from app.platform_utils import get_session_factory

    session_factory = get_session_factory()
    async with session_factory() as db:
        await db.execute(
            text("UPDATE chats SET deleted_at = :now WHERE id = :id"),
            {"now": datetime.now(timezone.utc), "id": chat_id},
        )
        await db.commit()


@pytest.mark.asyncio
async def test_mobile_sessions_lists_recent_finished_chat(async_client: httpx.AsyncClient) -> None:
    """已完成（非活跃）会话出现在 recentSessions，字段齐全且排除回收站。"""
    chat_id = str(uuid.uuid4())
    trashed_id = str(uuid.uuid4())
    await _create_chat(chat_id, title="Report Task", agent_id="agent-x")
    await _create_chat(trashed_id, title="Trashed Task")
    await _soft_delete_chat(trashed_id)

    resp = await async_client.get("/api/v1/remote-access/mobile/sessions")
    assert resp.status_code == 200
    data = resp.json()["data"]

    assert data["activeSessions"] == []
    recent_ids = [item["chatId"] for item in data["recentSessions"]]
    assert chat_id in recent_ids
    assert trashed_id not in recent_ids

    item = next(r for r in data["recentSessions"] if r["chatId"] == chat_id)
    assert item["title"] == "Report Task"
    assert item["agentId"] == "agent-x"
    # No agent profile row exists in the test DB, so the display name stays null.
    assert item["agentName"] is None
    assert isinstance(item["updatedAt"], str) and item["updatedAt"]
    assert data["maxConcurrent"] >= 1
    assert data["availableSlots"] >= 0


@pytest.mark.asyncio
async def test_pairing_mints_control_token_for_finished_chat(async_client: httpx.AsyncClient) -> None:
    """核心放宽：任务跑完后（非活跃）hub_list 仍可为该 chat 签发 control token。"""
    chat_id = str(uuid.uuid4())
    await _create_chat(chat_id, title="Finished Report")

    list_token = create_pairing_token(purpose=MOBILE_HUB_LIST_PURPOSE)
    resp = await async_client.post(
        "/api/v1/remote-access/pairing-token",
        headers={"X-Pair-Token": list_token},
        json={"chat_id": chat_id, "purpose": "mobile_hub"},
    )
    assert resp.status_code == 200
    body = resp.json()["data"]
    scoped_token = body["token"]
    assert body["mobilePath"] == f"/mobile/status/{chat_id}?pair={scoped_token}"

    parsed = parse_pairing_token(scoped_token)
    assert parsed is not None
    assert parsed["chat_id"] == chat_id
    assert parsed["purpose"] == MOBILE_HUB_CONTROL_PURPOSE


@pytest.mark.asyncio
async def test_pairing_rejects_trashed_chat(async_client: httpx.AsyncClient) -> None:
    """回收站会话（软删除）不签发 control token。"""
    chat_id = str(uuid.uuid4())
    await _create_chat(chat_id, title="Soon Trashed")
    await _soft_delete_chat(chat_id)

    list_token = create_pairing_token(purpose=MOBILE_HUB_LIST_PURPOSE)
    resp = await async_client.post(
        "/api/v1/remote-access/pairing-token",
        headers={"X-Pair-Token": list_token},
        json={"chat_id": chat_id, "purpose": "mobile_hub"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_pairing_rejects_missing_chat(async_client: httpx.AsyncClient) -> None:
    """不存在的 chat 不签发 control token。"""
    list_token = create_pairing_token(purpose=MOBILE_HUB_LIST_PURPOSE)
    resp = await async_client.post(
        "/api/v1/remote-access/pairing-token",
        headers={"X-Pair-Token": list_token},
        json={"chat_id": f"ghost-{uuid.uuid4()}", "purpose": "mobile_hub"},
    )
    assert resp.status_code == 404
