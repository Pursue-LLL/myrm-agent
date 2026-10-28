"""Password-gate lockout of the public chat share route (real router, stubbed chat lookup and rendering)."""

from __future__ import annotations

import asyncio
import json
from collections import Counter
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient

from app.api.chats.chat.share import public_router
from app.core.security.share.share_hmac import b64url_encode, token_fingerprint
from app.core.security.share.share_unlock import unlock_cookie_name
from app.database.connection import get_db

if TYPE_CHECKING:
    from httpx2 import Response  # the response type starlette's TestClient returns
from app.database.dto import ChatDTO
from app.services.chat.share_token import create_chat_share_token

_PASSWORD = "s3cret"
_BASE = "/public/chat-share"


def _chat(chat_id: str) -> ChatDTO:
    now = datetime.now(timezone.utc)
    return ChatDTO(
        id=chat_id,
        agent_id="agent-1",
        title="Test Chat",
        first_message="Hello",
        created_at=now,
        updated_at=now,
    )


async def _lookup_chat(chat_id: str) -> ChatDTO:
    # A real suspension point ahead of the password gate, so concurrent requests interleave there like they do against
    # the database-backed chat lookup.
    await asyncio.sleep(0)
    return _chat(chat_id)


@pytest.fixture
def share_app() -> Iterator[FastAPI]:
    app = FastAPI()
    app.include_router(public_router, prefix=_BASE)

    async def _no_db() -> None:
        return None

    app.dependency_overrides[get_db] = _no_db
    with (
        patch("app.services.chat.chat_service.ChatService.get_chat_metadata", new=AsyncMock(side_effect=_lookup_chat)),
        patch("app.api.chats.chat.share.public.render_share_html", new=AsyncMock(return_value="<html>shared</html>")),
    ):
        yield app


@pytest.fixture
def client(share_app: FastAPI) -> Iterator[TestClient]:
    with TestClient(share_app) as test_client:
        yield test_client


def _protected_token(chat_id: str = "chat-1") -> str:
    token, _ = create_chat_share_token(chat_id, ttl_seconds=3600, password=_PASSWORD)
    return token


def _guess(client: TestClient, token: str, password: str, *, post: bool = False) -> Response:
    if post:
        return client.post(f"{_BASE}/{token}", data={"p": password}, follow_redirects=False)
    return client.get(f"{_BASE}/{token}", params={"p": password}, follow_redirects=False)


def test_wrong_guesses_answer_403_then_the_sixth_attempt_is_429(client: TestClient) -> None:
    token = _protected_token()
    for _ in range(5):
        wrong = _guess(client, token, "wrong")
        assert wrong.status_code == 403
        assert "Incorrect password" in wrong.text

    locked = _guess(client, token, "wrong")

    assert locked.status_code == 429
    assert 60 < int(locked.headers["Retry-After"]) <= 300
    assert "Too many incorrect attempts" in locked.text


def test_gate_lock_and_status_pages_follow_the_visitor_language(client: TestClient) -> None:
    token = _protected_token()
    zh = {"Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"}

    gate = client.get(f"{_BASE}/{token}", headers=zh)
    assert gate.status_code == 403
    assert "需要密码" in gate.text

    for _ in range(4):
        client.get(f"{_BASE}/{token}", params={"p": "wrong"}, headers=zh)
    wrong = client.get(f"{_BASE}/{token}", params={"p": "wrong"}, headers=zh)
    assert "密码错误，请重试。" in wrong.text

    locked = client.get(f"{_BASE}/{token}", params={"p": "wrong"}, headers=zh)
    assert locked.status_code == 429
    assert "错误次数过多" in locked.text

    invalid = client.get(f"{_BASE}/not-a-share-token", headers={**zh, "Accept": "text/html"})
    assert invalid.status_code == 404
    assert "链接已过期" in invalid.text


def test_the_lock_is_reported_once_when_it_engages(client: TestClient) -> None:
    token = _protected_token()
    with patch("app.api.chats.chat.share.public.report_share_lockout", new=MagicMock()) as report:
        for _ in range(4):
            _guess(client, token, "wrong")
        report.assert_not_called()

        _guess(client, token, "wrong")
        report.assert_called_once()
        assert report.call_args.args[1] == token

        for _ in range(3):
            assert _guess(client, token, "wrong").status_code == 429
        report.assert_called_once()


def test_an_engaged_lock_reaches_the_auth_audit_trail_without_the_token(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    audit_file = tmp_path / "logs" / "auth_audit.jsonl"
    monkeypatch.setattr("app.middleware.auth_audit.AUDIT_LOG_FILE", audit_file)
    monkeypatch.setattr(
        "app.services.audit.lockout_events.get_deployment_capabilities", lambda: SimpleNamespace(enables_auth_audit=True)
    )
    token = _protected_token()
    for _ in range(8):
        _guess(client, token, "wrong")

    events = [json.loads(line) for line in audit_file.read_text(encoding="utf-8").splitlines()]
    assert len(events) == 1
    assert events[0]["type"] == "rate_limit_exceeded"
    assert events[0]["meta"] == {"scope": "share_password", "subject": token_fingerprint(token)[:12]}
    assert token not in audit_file.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_a_burst_of_concurrent_guesses_gets_exactly_five_tries(share_app: FastAPI) -> None:
    token = _protected_token()
    with patch("app.api.chats.chat.share.public.report_share_lockout", new=MagicMock()) as report:
        async with AsyncClient(transport=ASGITransport(app=share_app), base_url="http://testserver") as http:
            burst = await asyncio.gather(*(http.get(f"{_BASE}/{token}", params={"p": f"wrong-{i}"}) for i in range(60)))
            correct = await http.get(f"{_BASE}/{token}", params={"p": _PASSWORD})

    assert Counter(response.status_code for response in burst) == {403: 5, 429: 55}
    assert correct.status_code == 429
    report.assert_called_once()


def test_locked_share_rejects_even_the_correct_password(client: TestClient) -> None:
    token = _protected_token()
    for _ in range(5):
        _guess(client, token, "wrong", post=True)

    assert _guess(client, token, _PASSWORD).status_code == 429
    assert _guess(client, token, _PASSWORD, post=True).status_code == 429


def test_other_shares_are_unaffected(client: TestClient) -> None:
    locked_token = _protected_token("chat-1")
    other_token = _protected_token("chat-2")
    for _ in range(5):
        _guess(client, locked_token, "wrong")

    assert _guess(client, other_token, _PASSWORD).status_code == 200


def test_correct_password_resets_the_failure_count(client: TestClient) -> None:
    token = _protected_token()
    for _ in range(4):
        _guess(client, token, "wrong")
    assert _guess(client, token, _PASSWORD).status_code == 200

    for _ in range(4):
        assert _guess(client, token, "wrong").status_code == 403
    assert _guess(client, token, _PASSWORD).status_code == 200


def test_unlock_cookie_holders_are_not_locked_out(client: TestClient) -> None:
    token = _protected_token()
    unlocked = _guess(client, token, _PASSWORD)
    cookie_name = unlock_cookie_name("chat_share_unlock", token)
    cookie = unlocked.cookies.get(cookie_name)
    assert cookie is not None
    for _ in range(5):
        _guess(client, token, "wrong")

    revisit = client.get(f"{_BASE}/{token}", headers={"Cookie": f"{cookie_name}={cookie}"})

    assert revisit.status_code == 200


def test_requests_without_a_password_never_count(client: TestClient) -> None:
    token = _protected_token()
    for _ in range(10):
        assert client.get(f"{_BASE}/{token}").status_code == 403

    assert _guess(client, token, _PASSWORD).status_code == 200


def test_unprotected_links_never_lock(client: TestClient) -> None:
    token, _ = create_chat_share_token("chat-1", ttl_seconds=3600)
    for _ in range(10):
        assert _guess(client, token, "anything").status_code != 429


@pytest.mark.parametrize("body", [b"[1]", b"1", b'"x"', b"null"])
def test_token_with_a_non_object_body_is_an_invalid_link_not_a_server_error(client: TestClient, body: bytes) -> None:
    response = client.get(f"{_BASE}/{b64url_encode(body)}.sig", headers={"Accept": "application/json"})

    assert response.status_code == 404
