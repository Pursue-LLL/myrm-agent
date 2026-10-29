"""GET /chats/{chat_id}/export leaves out the system's notes about settled background tasks."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import httpx
import pytest
from httpx import ASGITransport

from app.database.models.chat import WAKEUP_NOTICE_KEY, Chat, Message
from app.platform_utils import get_session_factory
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


def _message(chat_id: str, role: str, content: str, extra_data: dict[str, object] | None = None) -> Message:
    return Message(
        id=f"msg-{uuid.uuid4().hex[:8]}",
        chat_id=chat_id,
        role=role,
        content=content,
        extra_data=extra_data,
        sent_at=datetime.now(tz=timezone.utc),
        sent_timezone="UTC",
    )


@pytest.mark.asyncio
async def test_export_leaves_out_the_systems_notes_about_settled_background_tasks(
    async_client: httpx.AsyncClient,
) -> None:
    chat_id = f"test-export-wake-{uuid.uuid4().hex[:8]}"
    async with get_session_factory()() as db:
        db.add(Chat(id=chat_id, title="Export Test Chat", action_mode="fast", source="web"))
        db.add(_message(chat_id, "user", "Hello, can you help me?"))
        db.add(_message(chat_id, "assistant", "Sure, I can help you with that."))
        db.add(
            _message(
                chat_id,
                "user",
                "<system_notification type='adaptive_settlement_degraded'>done</system_notification>",
                {WAKEUP_NOTICE_KEY: "degraded"},
            )
        )
        await db.commit()

    res = await async_client.get(f"/api/v1/chats/{chat_id}/export")
    assert res.status_code == 200, res.text

    contents = [m["content"] for m in res.json()["data"]["messages"]]
    assert sorted(contents) == ["Hello, can you help me?", "Sure, I can help you with that."]
