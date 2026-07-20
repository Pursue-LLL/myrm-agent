"""API tests for chat share create/revoke/render endpoints."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.chats.chat.share import public_router
from app.api.chats.chat.share import router as share_router
from app.core.infra.limiter import limiter
from app.database.connection import get_db
from app.database.dto import ChatDTO, MessageDTO


def _make_chat_dto(chat_id: str = "chat-1", share_revoked_at: datetime | None = None) -> ChatDTO:
    now = datetime.now(timezone.utc)
    return ChatDTO(
        id=chat_id,
        agent_id="agent-1",
        title="Test Chat",
        first_message="Hello there",
        created_at=now,
        updated_at=now,
        share_revoked_at=share_revoked_at,
    )


def _make_messages(chat_id: str = "chat-1") -> list[MessageDTO]:
    now = datetime.now(timezone.utc)
    return [
        MessageDTO(
            id="msg-1", chat_id=chat_id, role="user", content="Hello",
            sent_at=now, sent_timezone="UTC", created_at=now,
        ),
        MessageDTO(
            id="msg-2", chat_id=chat_id, role="assistant", content="Hi! How can I help?",
            sent_at=now, sent_timezone="UTC", created_at=now,
        ),
    ]


@pytest.fixture
def share_client() -> TestClient:
    limiter.enabled = False
    test_app = FastAPI()
    test_app.include_router(share_router, prefix="/chats")
    test_app.include_router(public_router, prefix="/public/chat-share")

    mock_db = MagicMock()
    mock_db.execute = AsyncMock(return_value=MagicMock())
    mock_db.commit = AsyncMock()

    async def override_get_db():
        yield mock_db

    test_app.dependency_overrides[get_db] = override_get_db
    with TestClient(test_app) as client:
        yield client


class TestCreateChatShare:
    def test_create_share_returns_url(self, share_client: TestClient) -> None:
        with patch(
            "app.api.chats.chat.share.ChatService.get_chat_metadata",
            new_callable=AsyncMock,
            return_value=_make_chat_dto(),
        ):
            resp = share_client.post("/chats/chat-1/share", json={"ttl_days": 7})
            assert resp.status_code == 200
            data = resp.json()
            assert "token" in data
            assert "share_url" in data
            assert data["chat_id"] == "chat-1"
            assert data["expires_at"] > 0
            assert "/public/chat-share/" in data["share_url"]

    def test_create_share_chat_not_found(self, share_client: TestClient) -> None:
        with patch(
            "app.api.chats.chat.share.ChatService.get_chat_metadata",
            new_callable=AsyncMock,
            return_value=None,
        ):
            resp = share_client.post("/chats/chat-999/share", json={"ttl_days": 7})
            assert resp.status_code == 404

    def test_create_share_ttl_validation(self, share_client: TestClient) -> None:
        with patch(
            "app.api.chats.chat.share.ChatService.get_chat_metadata",
            new_callable=AsyncMock,
            return_value=_make_chat_dto(),
        ):
            resp = share_client.post("/chats/chat-1/share", json={"ttl_days": 0})
            assert resp.status_code == 422

            resp = share_client.post("/chats/chat-1/share", json={"ttl_days": 31})
            assert resp.status_code == 422


class TestRevokeChatShare:
    def test_revoke_share(self, share_client: TestClient) -> None:
        with patch(
            "app.api.chats.chat.share.ChatService.get_chat_metadata",
            new_callable=AsyncMock,
            return_value=_make_chat_dto(),
        ):
            resp = share_client.delete("/chats/chat-1/share")
            assert resp.status_code == 204

    def test_revoke_share_not_found(self, share_client: TestClient) -> None:
        with patch(
            "app.api.chats.chat.share.ChatService.get_chat_metadata",
            new_callable=AsyncMock,
            return_value=None,
        ):
            resp = share_client.delete("/chats/chat-999/share")
            assert resp.status_code == 404


class TestPublicSharePage:
    def test_valid_token_returns_html(self, share_client: TestClient) -> None:
        from app.services.chat.share_token import create_chat_share_token

        token, _ = create_chat_share_token("chat-1", ttl_seconds=3600)

        with (
            patch(
                "app.api.chats.chat.share.ChatService.get_chat_metadata",
                new_callable=AsyncMock,
                return_value=_make_chat_dto(),
            ),
            patch(
                "app.api.chats.chat.share.render_share_html",
                new_callable=AsyncMock,
                return_value="<html><body>Shared</body></html>",
            ),
        ):
            resp = share_client.get(f"/public/chat-share/{token}")
            assert resp.status_code == 200
            assert "text/html" in resp.headers["content-type"]
            assert "X-Frame-Options" in resp.headers
            assert resp.headers["X-Frame-Options"] == "DENY"

    def test_expired_token_returns_404(self, share_client: TestClient) -> None:
        import time

        from app.services.chat.share_token import create_chat_share_token

        token, _ = create_chat_share_token("chat-1", ttl_seconds=60)
        future = int(time.time()) + 120
        with patch("app.services.chat.share_token.time.time", return_value=future):
            resp = share_client.get(f"/public/chat-share/{token}")
            assert resp.status_code == 404

    def test_revoked_share_returns_404(self, share_client: TestClient) -> None:
        from app.services.chat.share_token import create_chat_share_token

        token, _ = create_chat_share_token("chat-1", ttl_seconds=3600)
        revoked_chat = _make_chat_dto(share_revoked_at=datetime.now(timezone.utc))

        with patch(
            "app.api.chats.chat.share.ChatService.get_chat_metadata",
            new_callable=AsyncMock,
            return_value=revoked_chat,
        ):
            resp = share_client.get(f"/public/chat-share/{token}")
            assert resp.status_code == 404

    def test_invalid_token_returns_404(self, share_client: TestClient) -> None:
        resp = share_client.get("/public/chat-share/invalid-token-here")
        assert resp.status_code == 404
