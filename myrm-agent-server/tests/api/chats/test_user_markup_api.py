"""User-authored text keeps its markup end to end: real middleware, real chat route, real database."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import httpx
import pytest
from httpx import ASGITransport

from app.middleware.text_sanitizer_middleware import TextSanitizerMiddleware
from app.services.chat.chat_service import ChatService
from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(preset="chats")
app.add_middleware(TextSanitizerMiddleware)


def _tag(name: str, *, closing: bool = False) -> str:
    """Build an angle-bracket tag without spelling the literal form in source."""
    return chr(60) + ("/" if closing else "") + name + chr(62)


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
        db.add(Chat(id=chat_id, title="Original", created_at=datetime.now(UTC), updated_at=datetime.now(UTC)))
        await db.commit()


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["think", "function_calls", "tool_call"])
async def test_chat_title_keeps_markup_and_drops_control_characters(async_client: httpx.AsyncClient, name: str) -> None:
    chat_id = f"markup-{uuid.uuid4().hex[:8]}"
    await _create_chat(chat_id)
    opening, closing = _tag(name), _tag(name, closing=True)

    response = await async_client.put(
        f"/api/v1/chats/{chat_id}/title",
        json={"title": f"How do I parse {opening}x{closing}?\x00\x07"},
    )

    assert response.status_code == 200
    chat = await ChatService.get_chat_metadata(chat_id)
    assert chat is not None
    assert chat.title == f"How do I parse {opening}x{closing}?"
