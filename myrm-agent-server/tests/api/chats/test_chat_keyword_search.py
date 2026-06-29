"""
Tests for chat history keyword search via the GET /api/v1/chats/ endpoint.

Validates fuzzy matching on title and first_message fields,
SQL wildcard escaping for `%` and `_`, and empty-keyword passthrough.
"""

from __future__ import annotations

import uuid

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


async def _create_chat(chat_id: str, title: str, first_message: str = "") -> None:
    from datetime import datetime, timezone

    from app.database.models.chat import Chat
    from app.platform_utils import get_session_factory

    factory = get_session_factory()
    async with factory() as session:
        chat = Chat(
            id=chat_id,
            title=title,
            first_message=first_message,
            source="web",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        session.add(chat)
        await session.commit()


async def _cleanup_chat(chat_id: str) -> None:
    from app.database.models.chat import Chat
    from app.platform_utils import get_session_factory

    factory = get_session_factory()
    async with factory() as session:
        from sqlalchemy import delete

        await session.execute(delete(Chat).where(Chat.id == chat_id))
        await session.commit()


@pytest.mark.asyncio
class TestChatKeywordSearch:
    """Test suite for keyword search functionality in chat history API."""

    async def test_search_by_title(self, async_client: httpx.AsyncClient) -> None:
        chat_id = str(uuid.uuid4())
        try:
            await _create_chat(chat_id, title="架构设计讨论", first_message="你好")
            resp = await async_client.get("/api/v1/chats/", params={"keyword": "架构"})
            assert resp.status_code == 200
            items = resp.json()["data"]["items"]
            assert any(item["id"] == chat_id for item in items)
        finally:
            await _cleanup_chat(chat_id)

    async def test_search_by_first_message(self, async_client: httpx.AsyncClient) -> None:
        chat_id = str(uuid.uuid4())
        try:
            await _create_chat(chat_id, title="普通标题", first_message="帮我分析性能瓶颈")
            resp = await async_client.get("/api/v1/chats/", params={"keyword": "性能瓶颈"})
            assert resp.status_code == 200
            items = resp.json()["data"]["items"]
            assert any(item["id"] == chat_id for item in items)
        finally:
            await _cleanup_chat(chat_id)

    async def test_search_no_match(self, async_client: httpx.AsyncClient) -> None:
        resp = await async_client.get(
            "/api/v1/chats/", params={"keyword": f"nomatch_{uuid.uuid4().hex[:8]}"}
        )
        assert resp.status_code == 200
        items = resp.json()["data"]["items"]
        assert len(items) == 0

    async def test_search_empty_keyword_returns_all(self, async_client: httpx.AsyncClient) -> None:
        resp_no_kw = await async_client.get("/api/v1/chats/", params={"page": 1, "page_size": 5})
        resp_empty_kw = await async_client.get(
            "/api/v1/chats/", params={"keyword": "", "page": 1, "page_size": 5}
        )
        assert resp_no_kw.status_code == 200
        assert resp_empty_kw.status_code == 200
        assert resp_no_kw.json()["data"]["pagination"]["total"] == resp_empty_kw.json()["data"]["pagination"]["total"]

    async def test_wildcard_percent_escaped(self, async_client: httpx.AsyncClient) -> None:
        """Searching for literal '%' should not match all records."""
        chat_id = str(uuid.uuid4())
        try:
            await _create_chat(chat_id, title="100% 完成率")
            resp = await async_client.get("/api/v1/chats/", params={"keyword": "100%"})
            assert resp.status_code == 200
            items = resp.json()["data"]["items"]
            assert any(item["id"] == chat_id for item in items)

            resp2 = await async_client.get("/api/v1/chats/", params={"keyword": "%"})
            assert resp2.status_code == 200
        finally:
            await _cleanup_chat(chat_id)

    async def test_wildcard_underscore_escaped(self, async_client: httpx.AsyncClient) -> None:
        """Searching for literal '_' should not match single-char wildcard."""
        chat_id = str(uuid.uuid4())
        try:
            await _create_chat(chat_id, title="file_name_test")
            resp = await async_client.get("/api/v1/chats/", params={"keyword": "file_name"})
            assert resp.status_code == 200
            items = resp.json()["data"]["items"]
            assert any(item["id"] == chat_id for item in items)
        finally:
            await _cleanup_chat(chat_id)

    async def test_case_insensitive(self, async_client: httpx.AsyncClient) -> None:
        chat_id = str(uuid.uuid4())
        try:
            await _create_chat(chat_id, title="Python Architecture Review")
            resp = await async_client.get("/api/v1/chats/", params={"keyword": "python"})
            assert resp.status_code == 200
            items = resp.json()["data"]["items"]
            assert any(item["id"] == chat_id for item in items)
        finally:
            await _cleanup_chat(chat_id)
