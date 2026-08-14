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

    def test_create_share_uses_public_ingress_base(self, share_client: TestClient) -> None:
        """share_url is built from the public-ingress SSOT when configured."""
        with (
            patch(
                "app.api.chats.chat.share.ChatService.get_chat_metadata",
                new_callable=AsyncMock,
                return_value=_make_chat_dto(),
            ),
            patch(
                "app.api.chats.chat.share.get_public_ingress_base_url",
                new_callable=AsyncMock,
                return_value="https://myrm-x.example.com",
            ),
        ):
            resp = share_client.post("/chats/chat-1/share", json={"ttl_days": 7})
        assert resp.status_code == 200
        data = resp.json()
        assert data["share_url"].startswith("https://myrm-x.example.com/api/v1/public/chat-share/")

    def test_create_share_falls_back_to_request_base(self, share_client: TestClient) -> None:
        """Empty ingress degrades to the request origin so local links still work."""
        with (
            patch(
                "app.api.chats.chat.share.ChatService.get_chat_metadata",
                new_callable=AsyncMock,
                return_value=_make_chat_dto(),
            ),
            patch(
                "app.api.chats.chat.share.get_public_ingress_base_url",
                new_callable=AsyncMock,
                return_value="",
            ),
        ):
            resp = share_client.post("/chats/chat-1/share", json={"ttl_days": 7})
        assert resp.status_code == 200
        data = resp.json()
        assert data["share_url"].startswith("http://testserver/api/v1/public/chat-share/")

    def test_create_share_falls_back_when_ingress_fails(
        self, share_client: TestClient
    ) -> None:
        """Ingress resolution failure must not fail share creation."""
        with (
            patch(
                "app.api.chats.chat.share.ChatService.get_chat_metadata",
                new_callable=AsyncMock,
                return_value=_make_chat_dto(),
            ),
            patch(
                "app.api.chats.chat.share.get_public_ingress_base_url",
                new_callable=AsyncMock,
                side_effect=RuntimeError("ingress unavailable"),
            ),
        ):
            resp = share_client.post("/chats/chat-1/share", json={"ttl_days": 7})
        assert resp.status_code == 200
        data = resp.json()
        assert data["share_url"].startswith("http://testserver/api/v1/public/chat-share/")


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
            assert resp.headers["X-Robots-Tag"] == "noindex, nofollow"
            assert resp.headers["Cache-Control"] == "no-store"

    def test_expired_token_returns_404(self, share_client: TestClient) -> None:
        import time

        from app.services.chat.share_token import create_chat_share_token

        token, _ = create_chat_share_token("chat-1", ttl_seconds=60)
        future = int(time.time()) + 120
        with patch("app.core.security.share_hmac.time.time", return_value=future):
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

    def test_password_token_requires_gate(self, share_client: TestClient) -> None:
        """A password-protected chat share renders the gate until unlocked."""
        from app.services.chat.share_token import create_chat_share_token

        token, _ = create_chat_share_token("chat-1", ttl_seconds=3600, password="s3cret")
        resp = share_client.get(f"/public/chat-share/{token}")
        assert resp.status_code == 403
        assert "Password Required" in resp.text

    def test_password_token_unlocks_via_post_form(
        self, share_client: TestClient
    ) -> None:
        """The password is posted in the form body (CWE-598) and PRG-redirects.

        A successful POST answers 303 See Other to the clean GET URL and sets
        an unlock cookie, so the address bar never carries ``?p=...`` and the
        followed GET authenticates via the cookie without re-entering the
        password.
        """
        from app.services.chat.share_token import create_chat_share_token

        token, _ = create_chat_share_token("chat-1", ttl_seconds=3600, password="s3cret")
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
            resp = share_client.post(
                f"/public/chat-share/{token}",
                data={"p": "s3cret"},
                follow_redirects=False,
            )
        assert resp.status_code == 303
        assert resp.headers["location"].endswith(f"/public/chat-share/{token}")

        from app.core.security.share_unlock import unlock_cookie_name

        cookie = share_client.cookies.get(unlock_cookie_name("chat_share_unlock", token))
        assert cookie is not None

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
            content = share_client.get(
                f"/public/chat-share/{token}",
                headers={"Cookie": f"{unlock_cookie_name('chat_share_unlock', token)}={cookie}"},
            )
        assert content.status_code == 200
        assert "Shared" in content.text

    def test_password_token_unlock_cookie_skips_gate(
        self, share_client: TestClient
    ) -> None:
        """A valid unlock cookie lets a revisit skip the gate entirely."""
        from app.services.chat.share_token import create_chat_share_token

        token, _ = create_chat_share_token("chat-1", ttl_seconds=3600, password="s3cret")

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
            unlock = share_client.post(
                f"/public/chat-share/{token}",
                data={"p": "s3cret"},
                follow_redirects=False,
            )
        assert unlock.status_code == 303

        from app.core.security.share_unlock import unlock_cookie_name

        cookie = unlock.headers["set-cookie"].split(";")[0].split("=", 1)[1]
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
            resp = share_client.get(
                f"/public/chat-share/{token}",
                headers={"Cookie": f"{unlock_cookie_name('chat_share_unlock', token)}={cookie}"},
            )
        assert resp.status_code == 200
        assert "Shared" in resp.text

    def test_password_token_short_remaining_serves_directly(
        self, share_client: TestClient
    ) -> None:
        """POST unlock with <60s remaining serves content instead of 303-looping."""
        import time

        from app.core.security.share_hmac import sign_share_token

        token = sign_share_token(
            {"cid": "chat-1", "p": 1},
            salt="chat-share",
            exp=int(time.time()) + 30,
            password="s3cret",
        )
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
            resp = share_client.post(
                f"/public/chat-share/{token}",
                data={"p": "s3cret"},
                follow_redirects=False,
            )
        assert resp.status_code == 200
        assert "Shared" in resp.text
        assert "set-cookie" not in resp.headers

    def test_password_token_query_still_unlocks(self, share_client: TestClient) -> None:
        """A password carried in the URL query still unlocks."""
        from app.services.chat.share_token import create_chat_share_token

        token, _ = create_chat_share_token("chat-1", ttl_seconds=3600, password="s3cret")
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
            resp = share_client.get(f"/public/chat-share/{token}?p=s3cret")
        assert resp.status_code == 200
        assert "Shared" in resp.text

    def test_password_token_wrong_password_via_post(
        self, share_client: TestClient
    ) -> None:
        """A wrong password posted via the form renders the gate again."""
        from app.services.chat.share_token import create_chat_share_token

        token, _ = create_chat_share_token("chat-1", ttl_seconds=3600, password="s3cret")
        resp = share_client.post(f"/public/chat-share/{token}", data={"p": "wrong"})
        assert resp.status_code == 403
        assert "Incorrect password" in resp.text
