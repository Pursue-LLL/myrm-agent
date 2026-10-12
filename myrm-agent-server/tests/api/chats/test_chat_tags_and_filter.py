"""
[INPUT] app.api.chats.chat.core::get_chats, update_chat_tags_endpoint
[OUTPUT] test_chat_tags_and_multi_dimensional_filtering
[POS] 聊天会话标签与多维度元数据过滤测试套件 (Item 156)。
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import httpx
import pytest
from httpx import ASGITransport

from app.database.models.chat import Chat
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


async def _create_test_chat(
    chat_id: str,
    title: str,
    tags: list[str],
    project_id: str | None = None,
    is_pinned: bool = False,
) -> None:
    session_factory = get_session_factory()
    async with session_factory() as db:
        chat = Chat(
            id=chat_id,
            title=title,
            tags=tags,
            project_id=project_id,
            is_pinned=is_pinned,
            action_mode="fast",
            source="web",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db.add(chat)
        await db.commit()


@pytest.mark.asyncio
async def test_update_chat_tags_endpoint(async_client: httpx.AsyncClient) -> None:
    chat_id = f"test-tag-{uuid.uuid4().hex[:8]}"
    await _create_test_chat(chat_id, "Test Chat for Tags", tags=["InitialTag"])

    # Update tags via PATCH endpoint
    response = await async_client.patch(
        f"/api/v1/chats/{chat_id}/tags",
        json={"tags": ["BugFix", "Security", "v2"]},
    )
    assert response.status_code == 200
    data = response.json().get("data", {})
    assert data.get("chatId") == chat_id
    assert set(data.get("tags", [])) == {"BugFix", "Security", "v2"}

    # Verify get_chats returns updated tags
    list_resp = await async_client.get("/api/v1/chats/", params={"keyword": "Test Chat for Tags"})
    assert list_resp.status_code == 200
    items = list_resp.json().get("data", {}).get("items", [])
    matched = [item for item in items if item["id"] == chat_id]
    assert len(matched) == 1
    assert set(matched[0]["tags"]) == {"BugFix", "Security", "v2"}


@pytest.mark.asyncio
async def test_multi_dimensional_filtering_tags(async_client: httpx.AsyncClient) -> None:
    unique_prefix = f"prefix-{uuid.uuid4().hex[:6]}"
    chat_1 = f"{unique_prefix}-1"
    chat_2 = f"{unique_prefix}-2"
    chat_3 = f"{unique_prefix}-3"

    await _create_test_chat(chat_1, f"{unique_prefix} Auth Bug", tags=["BugFix", "Auth"])
    await _create_test_chat(chat_2, f"{unique_prefix} Billing Refactor", tags=["Refactor", "Billing"])
    await _create_test_chat(chat_3, f"{unique_prefix} Auth Feature", tags=["Feature", "Auth"])

    # 1. Filter by single tag "BugFix"
    resp = await async_client.get("/api/v1/chats/", params={"tags": ["BugFix"], "keyword": unique_prefix})
    assert resp.status_code == 200
    items = resp.json().get("data", {}).get("items", [])
    ids = {item["id"] for item in items}
    assert chat_1 in ids
    assert chat_2 not in ids
    assert chat_3 not in ids

    # 2. Filter by multiple tags with match_mode="any" (Union)
    resp_any = await async_client.get(
        "/api/v1/chats/",
        params={"tags": ["BugFix", "Billing"], "match_mode": "any", "keyword": unique_prefix},
    )
    assert resp_any.status_code == 200
    items_any = resp_any.json().get("data", {}).get("items", [])
    ids_any = {item["id"] for item in items_any}
    assert chat_1 in ids_any
    assert chat_2 in ids_any
    assert chat_3 not in ids_any

    # 3. Filter by multiple tags with match_mode="all" (Intersection)
    resp_all = await async_client.get(
        "/api/v1/chats/",
        params={"tags": ["Auth", "BugFix"], "match_mode": "all", "keyword": unique_prefix},
    )
    assert resp_all.status_code == 200
    items_all = resp_all.json().get("data", {}).get("items", [])
    ids_all = {item["id"] for item in items_all}
    assert chat_1 in ids_all
    assert chat_3 not in ids_all
