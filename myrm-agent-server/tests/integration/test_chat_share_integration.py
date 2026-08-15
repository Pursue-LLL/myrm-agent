"""Real chat share lifecycle integration test (no mocks on critical paths).

Runs the whole share chain against a real in-memory SQLite database, the real
``ChatService`` / ``ChatRepository`` (UoW), the real HTML renderer and real
HMAC token primitives through the full HTTP stack:

- create unprotected share -> status reflects active link -> public GET 200
- revoke -> status revoked -> public GET 404 -> recreate can never resurrect
  the old (revoked) link while the fresh link keeps working
- password-protected share -> gate -> unlock via cookie -> serve -> revoke -> dead
- expired link reports as unshared; deleted chat answers public GET 404
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from typing import AsyncGenerator
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.chats.chat.share import public_router, router
from app.core.infra.ingress import invalidate_public_ingress_cache
from app.core.infra.limiter import limiter
from app.core.security.share_hmac import sign_share_token
from app.core.security.share_unlock import unlock_cookie_name
from app.database.connection import get_db
from app.database.models import Base, Chat, Message

_PUBLIC_PREFIX = "/api/v1/public/chat-share"
_COOKIE_PREFIX = "chat_share_unlock"


@pytest.fixture()
async def db_engine():
    # StaticPool shares a single connection: ``:memory:`` SQLite would otherwise
    # give every new connection its own empty database. aiosqlite executes DB
    # work on a worker thread, so reusing the connection across event loops
    # (fixture loop, asyncio.run seeding, TestClient portal loop) is safe.
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture()
def client(db_engine) -> TestClient:
    """Real-DB FastAPI app with the chat share routers wired in."""
    limiter.enabled = False
    invalidate_public_ingress_cache()
    TestSessionLocal = sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)

    async def _real_session() -> AsyncGenerator[AsyncSession, None]:
        async with TestSessionLocal() as session:
            try:
                yield session
            finally:
                await session.close()

    test_app = FastAPI()
    test_app.include_router(router, prefix="/chats")
    test_app.include_router(public_router, prefix=_PUBLIC_PREFIX)
    test_app.dependency_overrides[get_db] = _real_session

    with (
        patch("app.platform_utils.get_session_factory", return_value=TestSessionLocal),
        patch(
            "app.database.connection.get_session_factory",
            return_value=TestSessionLocal,
        ),
        patch(
            "app.database.repositories.uow.get_session_factory",
            return_value=TestSessionLocal,
        ),
    ):
        with TestClient(test_app) as test_client:
            yield test_client

    limiter.enabled = True


def _insert_chat(db_engine, *, chat_id: str = "chat-1") -> None:
    """Insert a chat plus one message straight into the real database."""

    async def _insert() -> None:
        async with AsyncSession(db_engine) as session:
            now = datetime.now(timezone.utc)
            session.add(
                Chat(
                    id=chat_id,
                    title="Shared Conversation",
                    source="web",
                    action_mode="fast",
                    created_at=now,
                    updated_at=now,
                )
            )
            session.add(
                Message(
                    id=f"m-{chat_id}",
                    chat_id=chat_id,
                    role="user",
                    content="Hello world",
                    sent_at=now,
                    sent_timezone="UTC",
                )
            )
            await session.commit()

    asyncio.run(_insert())


def _delete_chat(db_engine, chat_id: str) -> None:
    async def _delete() -> None:
        async with AsyncSession(db_engine) as session:
            chat = await session.get(Chat, chat_id)
            if chat is not None:
                await session.delete(chat)
                await session.commit()

    asyncio.run(_delete())


def _expire_share(db_engine, chat_id: str) -> None:
    """Force the persisted share expiry into the past (past-due link)."""

    async def _update() -> None:
        async with AsyncSession(db_engine) as session:
            chat = await session.get(Chat, chat_id)
            assert chat is not None
            chat.share_token_expires_at = int(time.time()) - 10
            await session.commit()

    asyncio.run(_update())


def _set_legacy_share(db_engine, chat_id: str, *, protected: bool) -> None:
    """Plant a legacy share record: fingerprint persisted, no expiry stored."""

    async def _update() -> None:
        async with AsyncSession(db_engine) as session:
            chat = await session.get(Chat, chat_id)
            assert chat is not None
            chat.share_token_fingerprint = "legacy-fingerprint"
            chat.share_token_protected = protected
            chat.share_token_expires_at = None
            chat.share_revoked_at = None
            await session.commit()

    asyncio.run(_update())


class TestShareLifecycle:
    def test_full_lifecycle_unprotected(self, client: TestClient, db_engine) -> None:
        """Create -> status -> serve -> revoke -> status -> old link stays dead."""
        _insert_chat(db_engine)

        created = client.post("/chats/chat-1/share", json={"ttl_days": 7})
        assert created.status_code == 200
        data = created.json()
        assert data["chat_id"] == "chat-1"
        assert data["share_url"].startswith(f"http://testserver{_PUBLIC_PREFIX}/")

        token = data["token"]
        status = client.get("/chats/chat-1/share").json()
        assert status["shared"] is True
        assert status["revoked"] is False
        assert status["password_protected"] is False
        assert status["share_url"] == data["share_url"]

        page = client.get(f"{_PUBLIC_PREFIX}/{token}")
        assert page.status_code == 200
        assert "Shared Conversation" in page.text
        assert page.headers["X-Robots-Tag"] == "noindex, nofollow"
        assert page.headers["Cache-Control"] == "no-store"

        assert client.delete("/chats/chat-1/share").status_code == 204
        status = client.get("/chats/chat-1/share").json()
        assert status["shared"] is True
        assert status["revoked"] is True

        assert client.get(f"{_PUBLIC_PREFIX}/{token}").status_code == 404

        # Recreating must never resurrect the revoked link. Wait past the
        # current second first: tokens are deterministic HMACs (same payload +
        # same exp second => identical token), so a same-second recreate would
        # re-issue the revoked token and be fail-closed dead on purpose.
        time.sleep(1.1)
        recreated = client.post("/chats/chat-1/share", json={"ttl_days": 7}).json()
        assert recreated["token"] != token
        assert client.get(f"{_PUBLIC_PREFIX}/{token}").status_code == 404
        assert client.get(f"{_PUBLIC_PREFIX}/{recreated['token']}").status_code == 200

    def test_password_protected_full_flow(self, client: TestClient, db_engine) -> None:
        """Gate -> wrong password -> unlock cookie -> serve -> revoke -> dead."""
        _insert_chat(db_engine, chat_id="chat-pw")

        created = client.post("/chats/chat-pw/share", json={"ttl_days": 7, "password": "s3cret"})
        assert created.status_code == 200
        data = created.json()
        token = data["token"]
        assert data["password_protected"] is True

        status = client.get("/chats/chat-pw/share").json()
        assert status["shared"] is True
        assert status["password_protected"] is True
        # Password tokens are never rebuilt, so no link is returned.
        assert status["share_url"] is None

        assert client.get(f"{_PUBLIC_PREFIX}/{token}").status_code == 403

        wrong = client.post(f"{_PUBLIC_PREFIX}/{token}", data={"p": "nope"})
        assert wrong.status_code == 403

        unlock = client.post(
            f"{_PUBLIC_PREFIX}/{token}",
            data={"p": "s3cret"},
            follow_redirects=False,
        )
        assert unlock.status_code == 303
        cookie_name = unlock_cookie_name(_COOKIE_PREFIX, token)
        cookie_value = unlock.cookies.get(cookie_name)
        assert cookie_value is not None

        page = client.get(f"{_PUBLIC_PREFIX}/{token}", cookies={cookie_name: cookie_value})
        assert page.status_code == 200
        assert "Shared Conversation" in page.text

        assert client.delete("/chats/chat-pw/share").status_code == 204
        assert client.get(f"{_PUBLIC_PREFIX}/{token}", cookies={cookie_name: cookie_value}).status_code == 404

    def test_revoked_protected_link_answers_404_to_fresh_visitor(self, client: TestClient, db_engine) -> None:
        """A revoked password-protected link never shows a gate to a new visitor."""
        _insert_chat(db_engine, chat_id="chat-pwrvk")

        created = client.post("/chats/chat-pwrvk/share", json={"ttl_days": 7, "password": "s3cret"})
        token = created.json()["token"]

        assert client.delete("/chats/chat-pwrvk/share").status_code == 204

        page = client.get(
            f"{_PUBLIC_PREFIX}/{token}",
            headers={"Accept": "text/html"},
        )
        assert page.status_code == 404
        assert "Link Revoked" in page.text

    def test_password_in_url_query_param_unlocks(self, client: TestClient, db_engine) -> None:
        """GET ?p=... (legacy links carrying the password) serves the content directly."""
        _insert_chat(db_engine, chat_id="chat-pwq")

        created = client.post("/chats/chat-pwq/share", json={"ttl_days": 7, "password": "s3cret"})
        token = created.json()["token"]

        assert client.get(f"{_PUBLIC_PREFIX}/{token}").status_code == 403
        page = client.get(f"{_PUBLIC_PREFIX}/{token}", params={"p": "s3cret"})
        assert page.status_code == 200
        assert "Shared Conversation" in page.text
        assert client.get(f"{_PUBLIC_PREFIX}/{token}", params={"p": "nope"}).status_code == 403

    def test_expired_protected_link_reports_unshared(self, client: TestClient, db_engine) -> None:
        """A past-due password-protected share never surfaces as active."""
        _insert_chat(db_engine, chat_id="chat-pwexp")

        client.post("/chats/chat-pwexp/share", json={"ttl_days": 7, "password": "s3cret"})
        _expire_share(db_engine, "chat-pwexp")

        status = client.get("/chats/chat-pwexp/share").json()
        assert status["shared"] is False
        assert status["password_protected"] is False

    def test_legacy_share_without_expiry_reports_shared_status_only(self, client: TestClient, db_engine) -> None:
        """Pre-expiry records: a fingerprint with no stored expiry yields a status only.

        The unprotected legacy case reports shared without a rebuildable URL (the
        expiry is unknown); the protected legacy case reports the protected status.
        """
        _insert_chat(db_engine, chat_id="legacy-open")
        _set_legacy_share(db_engine, "legacy-open", protected=False)
        open_status = client.get("/chats/legacy-open/share").json()
        assert open_status["shared"] is True
        assert open_status["password_protected"] is False
        assert open_status["share_url"] is None
        assert open_status["expires_at"] is None

        _insert_chat(db_engine, chat_id="legacy-pw")
        _set_legacy_share(db_engine, "legacy-pw", protected=True)
        pw_status = client.get("/chats/legacy-pw/share").json()
        assert pw_status["shared"] is True
        assert pw_status["password_protected"] is True
        assert pw_status["share_url"] is None

    def test_unshared_chat(self, client: TestClient, db_engine) -> None:
        """A chat that was never shared reports unshared."""
        _insert_chat(db_engine)
        status = client.get("/chats/chat-1/share").json()
        assert status == {
            "shared": False,
            "revoked": False,
            "password_protected": False,
            "share_url": None,
            "expires_at": None,
        }

    def test_chat_not_found(self, client: TestClient) -> None:
        assert client.post("/chats/ghost/share", json={"ttl_days": 7}).status_code == 404
        assert client.get("/chats/ghost/share").status_code == 404
        assert client.delete("/chats/ghost/share").status_code == 404

    def test_expired_link_reports_unshared(self, client: TestClient, db_engine) -> None:
        """An expired link is invalid and a never-shared chat reports unshared."""
        _insert_chat(db_engine)

        token = sign_share_token(
            {"cid": "chat-1"},
            salt="chat-share",
            exp=int(time.time()) - 10,
        )
        page = client.get(f"{_PUBLIC_PREFIX}/{token}", headers={"Accept": "text/html"})
        assert page.status_code == 404
        assert "Link Expired" in page.text

        assert client.get("/chats/chat-1/share").json()["shared"] is False

    def test_deleted_chat_after_share(self, client: TestClient, db_engine) -> None:
        """Deleting a chat after sharing answers public GET 404."""
        _insert_chat(db_engine)
        created = client.post("/chats/chat-1/share", json={"ttl_days": 7})
        token = created.json()["token"]

        _delete_chat(db_engine, "chat-1")

        page = client.get(f"{_PUBLIC_PREFIX}/{token}", headers={"Accept": "text/html"})
        assert page.status_code == 404
        assert "Content Unavailable" in page.text
