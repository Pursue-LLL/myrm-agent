"""The Telegram connection test checks the token through the proxy the form carries."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

from app.channels.providers.telegram.api_core import TelegramApiError
from tests.support.minimal_app import build_minimal_app

_URL = "/api/v1/channels/manage/telegram/test"
_PROXY = "http://127.0.0.1:7890"

app = build_minimal_app(preset="channels_local")


@asynccontextmanager
async def _noop_lifespan(_app: object) -> AsyncIterator[None]:
    yield


@pytest.fixture
def client() -> Iterator[TestClient]:
    original_lifespan = app.router.lifespan_context
    app.router.lifespan_context = _noop_lifespan
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client
    app.router.lifespan_context = original_lifespan


@pytest.fixture
def telegram_client() -> Iterator[MagicMock]:
    with patch("app.channels.providers.telegram.api.TelegramClient") as constructor:
        constructor.return_value.get_me = AsyncMock(return_value={"username": "proxied_bot"})
        constructor.return_value.close = AsyncMock()
        yield constructor


@pytest.mark.parametrize(
    ("body", "expected_proxy"),
    [
        ({"botToken": "tok", "proxy": _PROXY}, _PROXY),
        ({"botToken": "tok", "proxy": ""}, None),
        ({"botToken": "tok"}, None),
    ],
    ids=["with_proxy", "empty_proxy", "no_proxy"],
)
def test_the_token_is_checked_through_the_proxy_of_the_form(
    client: TestClient, telegram_client: MagicMock, body: dict[str, str], expected_proxy: str | None
) -> None:
    response = client.post(_URL, json=body)

    assert response.status_code == 200
    assert response.json() == {"ok": True, "message": "Connected as @proxied_bot"}
    telegram_client.assert_called_once_with("tok", proxy=expected_proxy)


def test_an_unusable_proxy_is_reported_without_its_credentials(client: TestClient) -> None:
    response = client.post(_URL, json={"botToken": "tok", "proxy": "foo://user:hunter2@127.0.0.1:1"})

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    assert "hunter2" not in body["message"]
    assert body["reason"] == "TELEGRAM_UNREACHABLE"


@pytest.mark.parametrize(
    ("failure", "expected_reason"),
    [
        (TelegramApiError(401, "Unauthorized"), "TELEGRAM_TOKEN_REJECTED"),
        (TelegramApiError(404, "Not Found"), "TELEGRAM_TOKEN_REJECTED"),
        (httpx.ConnectError("All connection attempts failed"), "TELEGRAM_UNREACHABLE"),
    ],
    ids=["unknown_token", "malformed_token", "unreachable"],
)
def test_a_failed_check_says_why_it_failed(
    client: TestClient, telegram_client: MagicMock, failure: Exception, expected_reason: str
) -> None:
    telegram_client.return_value.get_me = AsyncMock(side_effect=failure)

    response = client.post(_URL, json={"botToken": "tok"})

    assert response.status_code == 200
    assert response.json() == {"ok": False, "message": str(failure), "reason": expected_reason}
