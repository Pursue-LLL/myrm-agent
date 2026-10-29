"""What revoking a conversation share actually withdraws, across several create / revoke rounds.

The real create, revoke and public routes run against one in-memory chat row, so what is asserted is what a visitor holding an
old link gets after the owner's last action, not what a single route happens to write.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Update
from sqlalchemy.sql.elements import BindParameter

from app.api.chats.chat.share import public_router
from app.api.chats.chat.share import router as share_router
from app.database.connection import get_db
from app.database.dto import ChatDTO
from app.services.chat.share_token import parse_chat_share_token

_CHAT_ID = "chat-1"
_TTL_SECONDS_PER_DAY = 24 * 3600
_SHARE_COLUMNS = (
    "share_revoked_at",
    "share_token_fingerprint",
    "share_revoked_fingerprints",
    "share_token_expires_at",
    "share_token_protected",
)


class _ChatRow:
    """The share columns of one chat, written by the routes' ``update()`` statements."""

    def __init__(self) -> None:
        self.columns: dict[str, object] = dict.fromkeys(_SHARE_COLUMNS)

    def as_dto(self) -> ChatDTO:
        now = datetime.now(timezone.utc)
        return ChatDTO.model_validate(
            {
                "id": _CHAT_ID,
                "agent_id": "agent-1",
                "title": "Test Chat",
                "first_message": "Hello",
                "created_at": now,
                "updated_at": now,
            }
            | self.columns
        )

    def apply(self, statement: object) -> MagicMock:
        if isinstance(statement, Update):
            for column, value in (statement._values or {}).items():
                self.columns[getattr(column, "key", str(column))] = value.value if isinstance(value, BindParameter) else value
        return MagicMock()


@pytest.fixture
def lifecycle() -> Iterator[tuple[TestClient, _ChatRow]]:
    row = _ChatRow()
    app = FastAPI()
    app.include_router(share_router, prefix="/chats")
    app.include_router(public_router, prefix="/public/chat-share")

    db = MagicMock()
    db.execute = AsyncMock(side_effect=row.apply)
    db.commit = AsyncMock()

    async def override_get_db() -> AsyncIterator[MagicMock]:
        yield db

    app.dependency_overrides[get_db] = override_get_db
    with (
        patch(
            "app.services.chat.chat_service.ChatService.get_chat_metadata", new=AsyncMock(side_effect=lambda _id: row.as_dto())
        ),
        patch("app.api.chats.chat.share.public.render_share_html", new=AsyncMock(return_value="<html>shared</html>")),
        TestClient(app) as client,
    ):
        yield client, row


def _create(client: TestClient, *, ttl_days: int, password: str | None = None) -> str:
    """Create a link and return its token. Distinct ``ttl_days`` keep tokens minted in one second distinct."""
    body: dict[str, object] = {"ttl_days": ttl_days}
    if password is not None:
        body["password"] = password
    response = client.post(f"/chats/{_CHAT_ID}/share", json=body)
    assert response.status_code == 200
    token = response.json()["token"]
    assert isinstance(token, str)
    return token


def _visit(client: TestClient, token: str) -> int:
    return client.get(f"/public/chat-share/{token}").status_code


def test_a_link_replaced_by_a_new_one_stays_dead_after_revoke_and_re_share(lifecycle: tuple[TestClient, _ChatRow]) -> None:
    client, _ = lifecycle
    first = _create(client, ttl_days=7)
    second = _create(client, ttl_days=14)

    assert client.delete(f"/chats/{_CHAT_ID}/share").status_code == 204
    third = _create(client, ttl_days=30)

    assert _visit(client, third) == 200
    assert _visit(client, second) == 404
    assert _visit(client, first) == 404


def test_creating_a_new_link_withdraws_the_one_before_it_at_once(lifecycle: tuple[TestClient, _ChatRow]) -> None:
    client, _ = lifecycle
    first = _create(client, ttl_days=7)
    assert _visit(client, first) == 200

    second = _create(client, ttl_days=14)

    assert _visit(client, second) == 200
    assert _visit(client, first) == 404


def test_a_password_protected_link_is_withdrawn_by_the_next_create_too(lifecycle: tuple[TestClient, _ChatRow]) -> None:
    client, row = lifecycle
    protected = _create(client, ttl_days=7, password="s3cret")
    plain = _create(client, ttl_days=14)

    assert row.columns["share_token_protected"] is False
    assert _visit(client, plain) == 200
    assert _visit(client, protected) == 404


def test_the_retired_set_holds_each_link_once(lifecycle: tuple[TestClient, _ChatRow]) -> None:
    client, row = lifecycle
    _create(client, ttl_days=7)
    _create(client, ttl_days=14)
    client.delete(f"/chats/{_CHAT_ID}/share")
    _create(client, ttl_days=21)
    client.delete(f"/chats/{_CHAT_ID}/share")

    retired = row.columns["share_revoked_fingerprints"]
    assert isinstance(retired, list)
    assert len(retired) == 3
    assert len(set(retired)) == 3


def test_creating_the_same_link_again_in_one_second_does_not_retire_it(lifecycle: tuple[TestClient, _ChatRow]) -> None:
    """Same chat, ttl and password within one second mint the identical token; retiring it would kill the new link."""
    client, row = lifecycle
    first = _create(client, ttl_days=7)
    claims = parse_chat_share_token(first)
    assert claims is not None
    minted_at = claims.exp - 7 * _TTL_SECONDS_PER_DAY
    with patch("app.core.security.share.share_hmac.time.time", return_value=minted_at):
        second = _create(client, ttl_days=7)

    assert second == first
    assert _visit(client, second) == 200
    assert not row.columns["share_revoked_fingerprints"]


def test_revoke_withdraws_the_current_link(lifecycle: tuple[TestClient, _ChatRow]) -> None:
    client, _ = lifecycle
    token = _create(client, ttl_days=7)

    assert client.delete(f"/chats/{_CHAT_ID}/share").status_code == 204

    assert _visit(client, token) == 404
