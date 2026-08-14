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


def _make_chat_dto(
    chat_id: str = "chat-1",
    share_revoked_at: datetime | None = None,
    share_token_fingerprint: str | None = None,
    share_revoked_fingerprints: list[str] | None = None,
    share_token_expires_at: int | None = None,
    share_token_protected: bool | None = None,
) -> ChatDTO:
    now = datetime.now(timezone.utc)
    return ChatDTO(
        id=chat_id,
        agent_id="agent-1",
        title="Test Chat",
        first_message="Hello there",
        created_at=now,
        updated_at=now,
        share_revoked_at=share_revoked_at,
        share_token_fingerprint=share_token_fingerprint,
        share_revoked_fingerprints=share_revoked_fingerprints,
        share_token_expires_at=share_token_expires_at,
        share_token_protected=share_token_protected,
    )


def _make_messages(chat_id: str = "chat-1") -> list[MessageDTO]:
    now = datetime.now(timezone.utc)
    return [
        MessageDTO(
            id="msg-1",
            chat_id=chat_id,
            role="user",
            content="Hello",
            sent_at=now,
            sent_timezone="UTC",
            created_at=now,
        ),
        MessageDTO(
            id="msg-2",
            chat_id=chat_id,
            role="assistant",
            content="Hi! How can I help?",
            sent_at=now,
            sent_timezone="UTC",
            created_at=now,
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
        client._mock_db = mock_db
        yield client


def _update_values_from_executes(mock_db: MagicMock) -> list[dict[str, object]]:
    """Return the ``values`` dict of every ``update()`` executed on the mock DB."""
    from sqlalchemy import Update
    from sqlalchemy.sql.elements import BindParameter

    captured: list[dict[str, object]] = []
    for call in mock_db.execute.call_args_list:
        stmt = call.args[0]
        if isinstance(stmt, Update):
            captured.append(
                {getattr(k, "key", str(k)): (v.value if isinstance(v, BindParameter) else v) for k, v in stmt._values.items()}
            )
    return captured


def _token_for_exp(exp: int, *, password: str | None = None) -> str:
    """Create a chat share token pinned to an explicit expiry.

    ``create_chat_share_token`` derives ``exp`` from the wall clock, so two
    tokens minted in the same second are identical; pinning ``exp`` guarantees
    distinct tokens that exercise per-token revocation semantics.
    """
    from app.core.security.share_hmac import sign_share_token

    payload: dict[str, object] = {"cid": "chat-1"}
    if password is not None:
        payload["p"] = 1
    return sign_share_token(
        payload,
        salt="chat-share",
        exp=exp,
        password=password,
    )


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
                "app.core.infra.ingress.get_public_ingress_base_url",
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
                "app.core.infra.ingress.get_public_ingress_base_url",
                new_callable=AsyncMock,
                return_value="",
            ),
        ):
            resp = share_client.post("/chats/chat-1/share", json={"ttl_days": 7})
        assert resp.status_code == 200
        data = resp.json()
        assert data["share_url"].startswith("http://testserver/api/v1/public/chat-share/")

    def test_create_persists_expiry_and_protected_flag(self, share_client: TestClient) -> None:
        """Create persists the display metadata the status endpoint needs."""
        with patch(
            "app.api.chats.chat.share.ChatService.get_chat_metadata",
            new_callable=AsyncMock,
            return_value=_make_chat_dto(),
        ):
            resp = share_client.post(
                "/chats/chat-1/share",
                json={"ttl_days": 7, "password": "s3cret"},
            )
        assert resp.status_code == 200
        values = _update_values_from_executes(share_client._mock_db)
        assert len(values) == 1
        assert isinstance(values[0]["share_token_expires_at"], int)
        assert values[0]["share_token_protected"] is True

    def test_create_persists_unprotected_flag(self, share_client: TestClient) -> None:
        """An unprotected share persists a False protected flag (not NULL)."""
        with patch(
            "app.api.chats.chat.share.ChatService.get_chat_metadata",
            new_callable=AsyncMock,
            return_value=_make_chat_dto(),
        ):
            resp = share_client.post("/chats/chat-1/share", json={"ttl_days": 7})
        assert resp.status_code == 200
        values = _update_values_from_executes(share_client._mock_db)
        assert len(values) == 1
        assert values[0]["share_token_protected"] is False


class TestRebuildChatShareToken:
    def test_rebuild_matches_created_token(self) -> None:
        """Same payload + expiry yields the exact same token (deterministic HMAC)."""
        from app.services.chat.share_token import create_chat_share_token, rebuild_chat_share_token

        token, expires_at = create_chat_share_token("chat-1", ttl_seconds=3600)
        rebuilt = rebuild_chat_share_token("chat-1", expires_at_unix=expires_at)
        assert rebuilt == token

    def test_rebuild_differs_across_expiries(self) -> None:
        from app.services.chat.share_token import rebuild_chat_share_token

        a = rebuild_chat_share_token("chat-1", expires_at_unix=1_000_000)
        b = rebuild_chat_share_token("chat-1", expires_at_unix=1_000_100)
        assert a != b

    def test_rebuilt_token_parses_and_is_not_protected(self) -> None:
        from app.services.chat.share_token import parse_chat_share_token, rebuild_chat_share_token

        rebuilt = rebuild_chat_share_token("chat-1", expires_at_unix=2_000_000_000)
        claims = parse_chat_share_token(rebuilt)
        assert claims is not None
        assert claims.chat_id == "chat-1"
        assert claims.exp == 2_000_000_000
        assert claims.password_protected is False


class TestGetChatShareStatus:
    def _get_status(self, share_client: TestClient, chat: ChatDTO) -> dict[str, object]:
        with patch(
            "app.api.chats.chat.share.ChatService.get_chat_metadata",
            new_callable=AsyncMock,
            return_value=chat,
        ):
            resp = share_client.get("/chats/chat-1/share")
        assert resp.status_code == 200
        return resp.json()

    def test_unshared(self, share_client: TestClient) -> None:
        data = self._get_status(share_client, _make_chat_dto())
        assert data == {
            "shared": False,
            "revoked": False,
            "password_protected": False,
            "share_url": None,
            "expires_at": None,
        }

    def test_revoked_takes_precedence(self, share_client: TestClient) -> None:
        """A revoked chat reports revoked even if stale display metadata remains."""
        from app.core.security.share_hmac import token_fingerprint
        from app.services.chat.share_token import create_chat_share_token

        token, expires_at = create_chat_share_token("chat-1", ttl_seconds=3600)
        chat = _make_chat_dto(
            share_revoked_at=datetime.now(timezone.utc),
            share_token_fingerprint=token_fingerprint(token),
            share_token_expires_at=expires_at,
            share_token_protected=False,
        )
        data = self._get_status(share_client, chat)
        assert data["shared"] is True
        assert data["revoked"] is True
        assert data["share_url"] is None

    def test_active_unprotected_rebuilds_url(self, share_client: TestClient) -> None:
        from app.core.security.share_hmac import token_fingerprint
        from app.services.chat.share_token import create_chat_share_token, rebuild_chat_share_token

        token, expires_at = create_chat_share_token("chat-1", ttl_seconds=3600)
        chat = _make_chat_dto(
            share_token_fingerprint=token_fingerprint(token),
            share_token_expires_at=expires_at,
            share_token_protected=False,
        )
        data = self._get_status(share_client, chat)
        assert data["shared"] is True
        assert data["revoked"] is False
        assert data["password_protected"] is False
        assert data["expires_at"] == expires_at
        rebuilt_token = str(data["share_url"]).rsplit("/", 1)[-1]
        assert rebuilt_token == rebuild_chat_share_token("chat-1", expires_at_unix=expires_at)

    def test_expired_unprotected_reports_unshared(self, share_client: TestClient) -> None:
        """An expired unprotected link is treated as unshared, not active."""
        from app.core.security.share_hmac import token_fingerprint
        from app.services.chat.share_token import create_chat_share_token

        token, expires_at = create_chat_share_token("chat-1", ttl_seconds=1)
        chat = _make_chat_dto(
            share_token_fingerprint=token_fingerprint(token),
            share_token_expires_at=expires_at - 60,
            share_token_protected=False,
        )
        data = self._get_status(share_client, chat)
        assert data["shared"] is False
        assert data["share_url"] is None

    def test_password_protected_returns_status_only(self, share_client: TestClient) -> None:
        """Password-protected shares never rebuild a credential-less link."""
        from app.core.security.share_hmac import token_fingerprint
        from app.services.chat.share_token import create_chat_share_token

        token, expires_at = create_chat_share_token("chat-1", ttl_seconds=3600, password="s3cret")
        chat = _make_chat_dto(
            share_token_fingerprint=token_fingerprint(token),
            share_token_expires_at=expires_at,
            share_token_protected=True,
        )
        data = self._get_status(share_client, chat)
        assert data["shared"] is True
        assert data["password_protected"] is True
        assert data["share_url"] is None

    def test_stale_fingerprint_without_expiry(self, share_client: TestClient) -> None:
        """Legacy rows with a fingerprint but no expiry report shared without a URL."""
        chat = _make_chat_dto(share_token_fingerprint="legacy-fp")
        data = self._get_status(share_client, chat)
        assert data["shared"] is True
        assert data["share_url"] is None

    def test_chat_not_found(self, share_client: TestClient) -> None:
        with patch(
            "app.api.chats.chat.share.ChatService.get_chat_metadata",
            new_callable=AsyncMock,
            return_value=None,
        ):
            resp = share_client.get("/chats/chat-999/share")
        assert resp.status_code == 404

    def test_create_share_falls_back_when_ingress_fails(self, share_client: TestClient) -> None:
        """Ingress resolution failure must not fail share creation."""
        with (
            patch(
                "app.api.chats.chat.share.ChatService.get_chat_metadata",
                new_callable=AsyncMock,
                return_value=_make_chat_dto(),
            ),
            patch(
                "app.core.infra.ingress.get_public_ingress_base_url",
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

    def test_revoke_records_active_token_fingerprint(self, share_client: TestClient) -> None:
        """Revoke moves the active token fingerprint into the revoked set."""
        from app.core.security.share_hmac import token_fingerprint
        from app.services.chat.share_token import create_chat_share_token

        token, _ = create_chat_share_token("chat-1", ttl_seconds=3600)
        active = _make_chat_dto(share_token_fingerprint=token_fingerprint(token))

        with patch(
            "app.api.chats.chat.share.ChatService.get_chat_metadata",
            new_callable=AsyncMock,
            return_value=active,
        ):
            resp = share_client.delete("/chats/chat-1/share")
        assert resp.status_code == 204

        values = _update_values_from_executes(share_client._mock_db)
        assert len(values) == 1
        assert values[0]["share_revoked_fingerprints"] == [token_fingerprint(token)]
        assert values[0]["share_token_fingerprint"] is None
        assert "share_revoked_at" in values[0]

    def test_create_keeps_previous_token_valid(self, share_client: TestClient) -> None:
        """A fresh share persists the new fingerprint without retiring old links."""
        from app.core.security.share_hmac import token_fingerprint
        from app.services.chat.share_token import create_chat_share_token

        old_token, _ = create_chat_share_token("chat-1", ttl_seconds=3600)
        old_fp = token_fingerprint(old_token)
        active = _make_chat_dto(share_token_fingerprint=old_fp)

        with patch(
            "app.api.chats.chat.share.ChatService.get_chat_metadata",
            new_callable=AsyncMock,
            return_value=active,
        ):
            resp = share_client.post("/chats/chat-1/share", json={"ttl_days": 7})
        assert resp.status_code == 200

        values = _update_values_from_executes(share_client._mock_db)
        assert len(values) == 1
        new_fp = values[0]["share_token_fingerprint"]
        assert isinstance(new_fp, str) and new_fp != old_fp
        # Previously issued links are not retired: the revoked set is untouched.
        assert "share_revoked_fingerprints" not in values[0]
        assert "share_revoked_at" not in values[0]

    def test_create_after_revoke_keeps_old_fingerprint_revoked(self, share_client: TestClient) -> None:
        """Recreating a share after revoke clears the flag but keeps the set."""
        from app.core.security.share_hmac import token_fingerprint
        from app.services.chat.share_token import create_chat_share_token

        old_token, _ = create_chat_share_token("chat-1", ttl_seconds=3600)
        old_fp = token_fingerprint(old_token)
        revoked = _make_chat_dto(
            share_revoked_at=datetime.now(timezone.utc),
            share_token_fingerprint=None,
            share_revoked_fingerprints=[old_fp],
        )

        with patch(
            "app.api.chats.chat.share.ChatService.get_chat_metadata",
            new_callable=AsyncMock,
            return_value=revoked,
        ):
            resp = share_client.post("/chats/chat-1/share", json={"ttl_days": 7})
        assert resp.status_code == 200

        values = _update_values_from_executes(share_client._mock_db)
        assert len(values) == 1
        assert values[0]["share_revoked_at"] is None
        # The revoked-fingerprint set persists untouched (old tokens stay dead).
        assert "share_revoked_fingerprints" not in values[0]


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
            assert resp.headers["Referrer-Policy"] == "no-referrer"

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

    def test_expired_token_browser_gets_status_page(self, share_client: TestClient) -> None:
        """Browser visitors get a friendly HTML status page instead of JSON 404."""
        import time

        from app.services.chat.share_token import create_chat_share_token

        token, _ = create_chat_share_token("chat-1", ttl_seconds=60)
        future = int(time.time()) + 120
        with patch("app.core.security.share_hmac.time.time", return_value=future):
            resp = share_client.get(
                f"/public/chat-share/{token}",
                headers={"Accept": "text/html"},
            )
        assert resp.status_code == 404
        assert "text/html" in resp.headers["content-type"]
        assert resp.headers["X-Robots-Tag"] == "noindex, nofollow"
        assert resp.headers["Cache-Control"] == "no-store"
        assert "Link Expired" in resp.text

    def test_revoked_share_browser_gets_status_page(self, share_client: TestClient) -> None:
        """A revoked share answers browsers with a dedicated status page."""
        from app.services.chat.share_token import create_chat_share_token

        token, _ = create_chat_share_token("chat-1", ttl_seconds=3600)
        revoked_chat = _make_chat_dto(share_revoked_at=datetime.now(timezone.utc))

        with patch(
            "app.api.chats.chat.share.ChatService.get_chat_metadata",
            new_callable=AsyncMock,
            return_value=revoked_chat,
        ):
            resp = share_client.get(
                f"/public/chat-share/{token}",
                headers={"Accept": "text/html"},
            )
        assert resp.status_code == 404
        assert "text/html" in resp.headers["content-type"]
        assert resp.headers["X-Robots-Tag"] == "noindex, nofollow"
        assert "Link Revoked" in resp.text

    def test_invalid_token_browser_gets_status_page(self, share_client: TestClient) -> None:
        """Invalid tokens answer browsers with a status page and API clients with JSON."""
        resp = share_client.get(
            "/public/chat-share/invalid-token-here",
            headers={"Accept": "text/html"},
        )
        assert resp.status_code == 404
        assert "text/html" in resp.headers["content-type"]
        assert "Link Expired" in resp.text
        assert resp.headers["Referrer-Policy"] == "no-referrer"

        json_resp = share_client.get(
            "/public/chat-share/invalid-token-here",
            headers={"Accept": "application/json"},
        )
        assert json_resp.status_code == 404
        assert json_resp.headers["content-type"].startswith("application/json")

    def test_password_token_requires_gate(self, share_client: TestClient) -> None:
        """A password-protected chat share renders the gate until unlocked."""
        from app.services.chat.share_token import create_chat_share_token

        token, _ = create_chat_share_token("chat-1", ttl_seconds=3600, password="s3cret")
        resp = share_client.get(f"/public/chat-share/{token}")
        assert resp.status_code == 403
        assert "Password Required" in resp.text

    def test_password_token_unlocks_via_post_form(self, share_client: TestClient) -> None:
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

    def test_password_token_unlock_cookie_skips_gate(self, share_client: TestClient) -> None:
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

    def test_password_token_short_remaining_serves_directly(self, share_client: TestClient) -> None:
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

    def test_password_token_wrong_password_via_post(self, share_client: TestClient) -> None:
        """A wrong password posted via the form renders the gate again."""
        from app.services.chat.share_token import create_chat_share_token

        token, _ = create_chat_share_token("chat-1", ttl_seconds=3600, password="s3cret")
        resp = share_client.post(f"/public/chat-share/{token}", data={"p": "wrong"})
        assert resp.status_code == 403
        assert "Incorrect password" in resp.text

    def test_revoked_then_reshared_old_token_stays_404(self, share_client: TestClient) -> None:
        """A revoked link stays dead after a fresh share for the same chat.

        Regression: recreating a share used to clear ``share_revoked_at``,
        which resurrected every previously revoked token for that chat.
        """
        import time

        from app.core.security.share_hmac import token_fingerprint

        old_token = _token_for_exp(int(time.time()) + 3600)
        new_token = _token_for_exp(int(time.time()) + 7200)
        reshared = _make_chat_dto(
            share_token_fingerprint=token_fingerprint(new_token),
            share_revoked_fingerprints=[token_fingerprint(old_token)],
        )
        with (
            patch(
                "app.api.chats.chat.share.ChatService.get_chat_metadata",
                new_callable=AsyncMock,
                return_value=reshared,
            ),
            patch(
                "app.api.chats.chat.share.render_share_html",
                new_callable=AsyncMock,
                return_value="<html><body>Shared</body></html>",
            ),
        ):
            assert share_client.get(f"/public/chat-share/{old_token}").status_code == 404
            assert share_client.get(f"/public/chat-share/{new_token}").status_code == 200

    def test_revoked_then_reshared_old_token_browser_gets_revoked_page(self, share_client: TestClient) -> None:
        """Browser visitors see the revoked status page, not conversation content."""
        import time

        from app.core.security.share_hmac import token_fingerprint

        old_token = _token_for_exp(int(time.time()) + 3600)
        new_token = _token_for_exp(int(time.time()) + 7200)
        reshared = _make_chat_dto(
            share_token_fingerprint=token_fingerprint(new_token),
            share_revoked_fingerprints=[token_fingerprint(old_token)],
        )
        with patch(
            "app.api.chats.chat.share.ChatService.get_chat_metadata",
            new_callable=AsyncMock,
            return_value=reshared,
        ):
            resp = share_client.get(
                f"/public/chat-share/{old_token}",
                headers={"Accept": "text/html"},
            )
        assert resp.status_code == 404
        assert "Link Revoked" in resp.text

    def test_multi_cycle_revoked_tokens_never_resurrect(self, share_client: TestClient) -> None:
        """Tokens revoked across multiple revoke/recreate cycles stay dead."""
        import time

        from app.core.security.share_hmac import token_fingerprint

        t1 = _token_for_exp(int(time.time()) + 3600)
        t2 = _token_for_exp(int(time.time()) + 7200)
        t3 = _token_for_exp(int(time.time()) + 10800)
        f1, f2, f3 = (token_fingerprint(t) for t in (t1, t2, t3))
        state = _make_chat_dto(
            share_token_fingerprint=f3,
            share_revoked_fingerprints=[f1, f2],
        )
        with (
            patch(
                "app.api.chats.chat.share.ChatService.get_chat_metadata",
                new_callable=AsyncMock,
                return_value=state,
            ),
            patch(
                "app.api.chats.chat.share.render_share_html",
                new_callable=AsyncMock,
                return_value="<html><body>Shared</body></html>",
            ),
        ):
            assert share_client.get(f"/public/chat-share/{t1}").status_code == 404
            assert share_client.get(f"/public/chat-share/{t2}").status_code == 404
            assert share_client.get(f"/public/chat-share/{t3}").status_code == 200

    def test_revoked_password_token_stays_404_after_reshare(self, share_client: TestClient) -> None:
        """A revoked password-protected token still dies after a fresh share."""
        import time

        from app.core.security.share_hmac import token_fingerprint

        old_token = _token_for_exp(int(time.time()) + 3600, password="s3cret")
        new_token = _token_for_exp(int(time.time()) + 7200, password="s3cret")
        reshared = _make_chat_dto(
            share_token_fingerprint=token_fingerprint(new_token),
            share_revoked_fingerprints=[token_fingerprint(old_token)],
        )
        with (
            patch(
                "app.api.chats.chat.share.ChatService.get_chat_metadata",
                new_callable=AsyncMock,
                return_value=reshared,
            ),
            patch(
                "app.api.chats.chat.share.render_share_html",
                new_callable=AsyncMock,
                return_value="<html><body>Shared</body></html>",
            ),
        ):
            # Password must be supplied to reach the revoked check; even the
            # correct password cannot resurrect a revoked token.
            resp = share_client.get(f"/public/chat-share/{old_token}?p=s3cret")
            assert resp.status_code == 404
            assert share_client.get(f"/public/chat-share/{new_token}?p=s3cret").status_code == 200
