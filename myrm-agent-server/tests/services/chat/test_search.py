"""Chat search tests — _sanitize_snippet + FTS5 end-to-end

Covers:
- _sanitize_snippet XSS protection (unit)
- ChatService.search_messages FTS5 integration (real SQLite, no mocks)
- sent_at ISO serialization correctness
- GET /chats/search API endpoint routing & response
"""

from datetime import datetime, timezone

import pytest
from search_support import seed_chat_and_messages
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Chat, Message
from app.database.repositories.conversation_recall import ConversationRecallRepository
from app.services.chat.chat_helpers import _sanitize_snippet
from app.services.chat.chat_service import ChatService

# ─────────────────────────────────────────────
# 1. Unit tests for _sanitize_snippet
# ─────────────────────────────────────────────


class TestSanitizeSnippet:
    def test_plain_text_unchanged(self):
        assert _sanitize_snippet("hello world") == "hello world"

    def test_preserves_mark_tags(self):
        s = "found <mark>keyword</mark> here"
        assert "<mark>keyword</mark>" in _sanitize_snippet(s)

    def test_escapes_script_tag(self):
        s = '<script>alert("xss")</script> and <mark>safe</mark>'
        result = _sanitize_snippet(s)
        assert "<script>" not in result
        assert "&lt;script&gt;" in result
        assert "<mark>safe</mark>" in result

    def test_escapes_img_onerror(self):
        s = "<img src=x onerror=alert(1)> <mark>match</mark>"
        result = _sanitize_snippet(s)
        assert "<img" not in result
        assert "<mark>match</mark>" in result

    def test_escapes_html_entities(self):
        s = "a < b > c & d <mark>e</mark>"
        result = _sanitize_snippet(s)
        assert "&lt;" in result
        assert "&amp;" in result
        assert "<mark>e</mark>" in result

    def test_empty_string(self):
        assert _sanitize_snippet("") == ""

    def test_only_marks(self):
        s = "<mark>full match</mark>"
        assert _sanitize_snippet(s) == "<mark>full match</mark>"

    def test_nested_html_in_mark(self):
        s = "<mark><b>bold</b></mark>"
        result = _sanitize_snippet(s)
        assert "<b>" not in result
        assert "<mark>&lt;b&gt;bold&lt;/b&gt;</mark>" == result

    def test_multiple_marks(self):
        s = "before <mark>a</mark> middle <mark>b</mark> after"
        result = _sanitize_snippet(s)
        assert result.count("<mark>") == 2
        assert result.count("</mark>") == 2

    def test_code_snippet_with_html(self):
        s = 'use <div class="foo"> <mark>example</mark>'
        result = _sanitize_snippet(s)
        assert "<div" not in result
        assert "<mark>example</mark>" in result


# ─────────────────────────────────────────────
# 2. FTS5 integration tests (real SQLite)
# ─────────────────────────────────────────────


class TestChatServiceSearch:
    @pytest.mark.asyncio
    async def test_search_finds_matching_messages(self, fts_db: AsyncSession):
        await seed_chat_and_messages(fts_db)
        items, total = await ChatService.search_messages("docker")
        assert total > 0
        assert any("docker" in item["content"].lower() for item in items)

    @pytest.mark.asyncio
    async def test_search_returns_snippet_with_highlight(self, fts_db: AsyncSession):
        await seed_chat_and_messages(fts_db)
        items, _ = await ChatService.search_messages("Kubernetes")
        assert len(items) > 0
        for item in items:
            assert "snippet" in item
            assert isinstance(item["snippet"], str)

    @pytest.mark.asyncio
    async def test_search_returns_chat_title(self, fts_db: AsyncSession):
        await seed_chat_and_messages(fts_db)
        items, _ = await ChatService.search_messages("docker")
        assert len(items) > 0
        assert items[0]["chat_title"] == "Docker deployment discussion"

    @pytest.mark.asyncio
    async def test_search_sent_at_is_iso_string(self, fts_db: AsyncSession):
        await seed_chat_and_messages(fts_db)
        items, _ = await ChatService.search_messages("docker")
        assert len(items) > 0
        for item in items:
            assert isinstance(item["sent_at"], str)
            datetime.fromisoformat(item["sent_at"])

    @pytest.mark.asyncio
    async def test_search_no_results(self, fts_db: AsyncSession):
        await seed_chat_and_messages(fts_db)
        items, total = await ChatService.search_messages("nonexistent_xyz_query")
        assert total == 0
        assert items == []

    @pytest.mark.asyncio
    async def test_search_excludes_inactive_messages(self, fts_db: AsyncSession):
        await seed_chat_and_messages(fts_db)
        await fts_db.execute(text("UPDATE messages SET is_active = 0 WHERE id = 'msg-1'"))
        await fts_db.commit()

        items, _ = await ChatService.search_messages("Compose")

        assert all(item["id"] != "msg-1" for item in items)

    @pytest.mark.asyncio
    async def test_search_respects_recall_exclusion(self, fts_db: AsyncSession):
        chat_id = await seed_chat_and_messages(fts_db)
        await ConversationRecallRepository.set_excluded(fts_db, chat_id, True)
        await fts_db.commit()

        items, total = await ChatService.search_messages("docker")

        assert total == 0
        assert items == []

    @pytest.mark.asyncio
    async def test_search_empty_query(self, fts_db: AsyncSession):
        await seed_chat_and_messages(fts_db)
        items, total = await ChatService.search_messages("")
        assert total == 0
        assert items == []

    @pytest.mark.asyncio
    async def test_search_pagination(self, fts_db: AsyncSession):
        await seed_chat_and_messages(fts_db)
        items_page1, total = await ChatService.search_messages("deploy", limit=1, offset=0)
        items_page2, _ = await ChatService.search_messages("deploy", limit=1, offset=1)
        assert len(items_page1) <= 1
        if total > 1:
            assert items_page1[0]["id"] != items_page2[0]["id"]

    @pytest.mark.asyncio
    async def test_search_snippet_is_sanitized(self, fts_db: AsyncSession):
        """Ensure snippets don't contain raw HTML (except <mark>)."""
        chat_id = "chat-xss-test"
        chat = Chat(id=chat_id, title="XSS test", action_mode="fast")
        fts_db.add(chat)
        msg = Message(
            id="msg-xss",
            chat_id=chat_id,
            role="user",
            content='<script>alert("xss")</script> some docker text',
            sent_at=datetime(2026, 4, 17, tzinfo=timezone.utc),
            sent_timezone="UTC",
        )
        fts_db.add(msg)
        await fts_db.commit()

        items, _ = await ChatService.search_messages("docker")
        xss_items = [i for i in items if i["id"] == "msg-xss"]
        assert len(xss_items) == 1
        snippet = xss_items[0]["snippet"]
        assert "<script>" not in snippet

    @pytest.mark.asyncio
    async def test_search_with_since_filter(self, fts_db: AsyncSession):
        """since parameter should exclude messages before the cutoff."""
        await seed_chat_and_messages(fts_db)
        future = datetime(2099, 1, 1, tzinfo=timezone.utc)
        items, total = await ChatService.search_messages("docker", since=future)
        assert total == 0

    @pytest.mark.asyncio
    async def test_search_with_until_filter(self, fts_db: AsyncSession):
        """until parameter should exclude messages after the cutoff."""
        await seed_chat_and_messages(fts_db)
        past = datetime(2020, 1, 1, tzinfo=timezone.utc)
        items, total = await ChatService.search_messages("docker", until=past)
        assert total == 0

    @pytest.mark.asyncio
    async def test_search_with_valid_time_range(self, fts_db: AsyncSession):
        """Messages within the time range should be returned."""
        await seed_chat_and_messages(fts_db)
        since = datetime(2026, 4, 1, tzinfo=timezone.utc)
        until = datetime(2026, 5, 1, tzinfo=timezone.utc)
        items, total = await ChatService.search_messages("docker", since=since, until=until)
        assert total > 0

    @pytest.mark.asyncio
    async def test_search_without_time_filter_returns_matches(self, fts_db: AsyncSession):
        """Without since/until, matching messages are returned."""
        await seed_chat_and_messages(fts_db)
        items, total = await ChatService.search_messages("docker")
        assert total > 0

    @pytest.mark.asyncio
    async def test_search_returns_role(self, fts_db: AsyncSession):
        await seed_chat_and_messages(fts_db)
        items, _ = await ChatService.search_messages("docker")
        roles = {item["role"] for item in items}
        assert roles.issubset({"user", "assistant"})

    @pytest.mark.asyncio
    async def test_search_returns_message_fields(self, fts_db: AsyncSession):
        """Verify all expected fields are present in search results."""
        await seed_chat_and_messages(fts_db)
        items, _ = await ChatService.search_messages("docker")
        assert len(items) > 0
        expected_fields = {"id", "chat_id", "role", "content", "sent_at", "chat_title", "snippet"}
        for item in items:
            assert expected_fields.issubset(item.keys())


# ─────────────────────────────────────────────
# 3. API endpoint tests (route registration)
# ─────────────────────────────────────────────


class TestSearchAPIEndpoint:
    """Test GET /chats/search route registration and parameter validation."""

    @pytest.fixture
    def search_client(self, fts_db: AsyncSession):
        """Build a minimal FastAPI test client with the chats router."""
        from importlib import import_module

        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        app = FastAPI()
        chat_module = import_module("app.api.chats.chat")
        app.include_router(chat_module.router, prefix="/api/v1/chats")

        async def mock_get_deploy_identity():
            return "test-user-id"

        pass

        async def mock_get_db():
            yield fts_db

        from app.database.connection import get_db

        app.dependency_overrides[get_db] = mock_get_db

        return TestClient(app)

    def test_search_endpoint_exists(self, search_client):
        """GET /chats/search should not 404."""
        resp = search_client.get("/api/v1/chats/search", params={"q": "test"})
        assert resp.status_code != 404

    def test_search_requires_query_param(self, search_client):
        """Missing q param should return 422."""
        resp = search_client.get("/api/v1/chats/search")
        assert resp.status_code == 422

    def test_search_min_length_validation(self, search_client):
        """Empty q should be rejected."""
        resp = search_client.get("/api/v1/chats/search", params={"q": ""})
        assert resp.status_code == 422

    def test_search_returns_success_structure(self, search_client, fts_db):
        """Response should match StandardSuccessResponse structure."""
        resp = search_client.get("/api/v1/chats/search", params={"q": "anything"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "data" in data
        assert "items" in data["data"]
        assert "total" in data["data"]

    def test_search_does_not_clash_with_chat_id_route(self, search_client):
        """/chats/search should not be captured by /chats/{chat_id}."""
        resp = search_client.get("/api/v1/chats/search", params={"q": "test"})
        assert resp.status_code == 200

    def test_recall_entries_does_not_clash_with_chat_id_route(self, search_client):
        """/chats/recall/entries should not be captured by /chats/{chat_id}."""
        resp = search_client.get("/api/v1/chats/recall/entries")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "items" in data["data"]

    def test_search_limit_param(self, search_client):
        """Custom limit should be accepted."""
        resp = search_client.get("/api/v1/chats/search", params={"q": "test", "limit": 5})
        assert resp.status_code == 200

    def test_search_offset_param(self, search_client):
        """Custom offset should be accepted."""
        resp = search_client.get("/api/v1/chats/search", params={"q": "test", "offset": 10})
        assert resp.status_code == 200

    def test_search_since_param_accepted(self, search_client):
        """since ISO 8601 parameter should be accepted."""
        resp = search_client.get(
            "/api/v1/chats/search",
            params={"q": "test", "since": "2026-04-01T00:00:00"},
        )
        assert resp.status_code == 200

    def test_search_until_param_accepted(self, search_client):
        """until ISO 8601 parameter should be accepted."""
        resp = search_client.get(
            "/api/v1/chats/search",
            params={"q": "test", "until": "2026-04-30T23:59:59"},
        )
        assert resp.status_code == 200

    def test_search_both_time_params(self, search_client):
        """Both since and until should be accepted together."""
        resp = search_client.get(
            "/api/v1/chats/search",
            params={
                "q": "test",
                "since": "2026-04-01T00:00:00",
                "until": "2026-04-30T23:59:59",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
