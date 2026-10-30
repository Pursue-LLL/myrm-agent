"""How a failed Telegram token check reaches the onboarding wizard: which failure it was, and whether a proxy was in play."""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api.config.router import _telegram_verification_error
from app.channels.providers.telegram.api_core import TelegramApiError
from app.database.connection import init_database
from tests.support.minimal_app import build_minimal_app

TEST_WS = Path(os.environ["MYRM_DATA_DIR"])
TEST_DB = TEST_WS / "data.db"

app = build_minimal_app(preset="config")

_APPLY_URL = "/api/v1/config/onboarding/telegram-assistant/apply"
_SAVED_PROXY = "http://127.0.0.1:7890"
_TOKEN_REJECTED = "TELEGRAM_TOKEN_REJECTED"
_UNREACHABLE = "TELEGRAM_UNREACHABLE"


@asynccontextmanager
async def _noop_lifespan(_app: object) -> AsyncIterator[None]:
    yield


@pytest.fixture(scope="module", autouse=True)
def setup_test_database() -> Iterator[None]:
    asyncio.run(init_database())
    yield
    from tests.api.config.conftest import cleanup_shared_test_db

    cleanup_shared_test_db(TEST_DB)


@pytest.fixture
def client() -> Iterator[TestClient]:
    original_lifespan = app.router.lifespan_context
    app.router.lifespan_context = _noop_lifespan
    try:
        with (
            patch("app.core.security.auth.identity.is_loopback_ip", return_value=True),
            patch("app.api.config.router._try_hot_register_channel", new=AsyncMock()),
            TestClient(app, base_url="http://127.0.0.1", raise_server_exceptions=False) as test_client,
        ):
            yield test_client
    finally:
        app.router.lifespan_context = original_lifespan


def _save_credentials(client: TestClient, value: dict[str, object]) -> None:
    response = client.put("/api/v1/config/telegramCredentials", json={"value": value, "deviceId": "test-suite"})
    assert response.status_code == 200


def _saved_credentials(client: TestClient) -> dict[str, object]:
    value = client.get("/api/v1/config/telegramCredentials").json()["value"]
    assert isinstance(value, dict)
    return value


def _apply(client: TestClient, **extra: str) -> httpx.Response:
    return client.post(_APPLY_URL, json={"botToken": "1234567890:SOME_TOKEN", "assistantName": "Assistant", **extra})


@pytest.mark.parametrize(
    ("failure", "proxy", "expected"),
    [
        (
            TelegramApiError(401, "Unauthorized"),
            None,
            {"code": _TOKEN_REJECTED, "message": "Telegram rejected the bot token"},
        ),
        (
            TelegramApiError(404, "Not Found"),
            "socks5://127.0.0.1:1080",
            {"code": _TOKEN_REJECTED, "message": "Telegram rejected the bot token"},
        ),
        (
            httpx.ConnectError("All connection attempts failed"),
            None,
            {"code": _UNREACHABLE, "message": "Telegram Bot API could not be reached", "viaProxy": False},
        ),
        (
            httpx.ReadTimeout("timed out"),
            "socks5://127.0.0.1:1080",
            {"code": _UNREACHABLE, "message": "Telegram Bot API could not be reached", "viaProxy": True},
        ),
    ],
)
def test_the_failure_detail_names_the_cause_and_only_an_unreachable_one_says_whether_a_proxy_was_used(
    failure: Exception, proxy: str | None, expected: dict[str, object]
) -> None:
    error = _telegram_verification_error(failure, proxy)

    assert error.status_code == 400
    assert error.detail == expected


@pytest.mark.parametrize(
    ("failure", "expected_code"),
    [
        (TelegramApiError(401, "Unauthorized"), _TOKEN_REJECTED),
        (TelegramApiError(404, "Not Found"), _TOKEN_REJECTED),
        (httpx.ConnectError("All connection attempts failed"), _UNREACHABLE),
        (httpx.ReadTimeout("timed out"), _UNREACHABLE),
        (TelegramApiError(429, "Too Many Requests"), _UNREACHABLE),
    ],
)
def test_apply_telegram_onboarding_tells_a_refused_token_from_an_unreachable_bot_api(
    client: TestClient, failure: Exception, expected_code: str
) -> None:
    _save_credentials(client, {"botToken": "old-token"})
    with (
        patch("app.api.config.router._verify_telegram_token", new=AsyncMock(side_effect=failure)),
        patch("app.services.agent.agent_service.AgentService.create_agent", new=AsyncMock()) as create_agent_mock,
    ):
        response = _apply(client)

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail["code"] == expected_code
    assert detail.get("viaProxy") is (False if expected_code == _UNREACHABLE else None)
    create_agent_mock.assert_not_awaited()


def test_an_unreachable_check_through_the_proxy_saved_earlier_is_reported_as_going_through_a_proxy(
    client: TestClient,
) -> None:
    """The wizard never shows the saved proxy and a blank field keeps it, so only the server knows one was used."""
    _save_credentials(client, {"botToken": "old-token", "proxy": _SAVED_PROXY})
    verify_token = AsyncMock(side_effect=httpx.ConnectError("All connection attempts failed"))
    with patch("app.api.config.router._verify_telegram_token", new=verify_token):
        response = _apply(client)

    assert response.status_code == 400
    assert response.json()["detail"] == {
        "code": _UNREACHABLE,
        "message": "Telegram Bot API could not be reached",
        "viaProxy": True,
    }
    verify_token.assert_awaited_once_with("1234567890:SOME_TOKEN", _SAVED_PROXY)


def test_apply_telegram_onboarding_keeps_the_saved_proxy_when_the_token_check_through_a_new_one_fails(
    client: TestClient,
) -> None:
    _save_credentials(client, {"botToken": "old-token", "proxy": _SAVED_PROXY})
    verify_token = AsyncMock(side_effect=httpx.ConnectError("All connection attempts failed"))
    with patch("app.api.config.router._verify_telegram_token", new=verify_token):
        response = _apply(client, proxy="http://127.0.0.1:8080")

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == _UNREACHABLE
    assert response.json()["detail"]["viaProxy"] is True
    verify_token.assert_awaited_once_with("1234567890:SOME_TOKEN", "http://127.0.0.1:8080")
    saved = _saved_credentials(client)
    assert saved["botToken"] == "old-token"
    assert saved["proxy"] == _SAVED_PROXY


def test_telegram_verification_failure_log_does_not_carry_the_bot_token(caplog: pytest.LogCaptureFixture) -> None:
    token = "1234567890:ABCdefGHIjklMNOpqrSTUvwxYZ0123456789"
    failure = httpx.ConnectError(f"connection failed for https://api.telegram.org/bot{token}/getMe")

    with caplog.at_level(logging.WARNING, logger="app.api.config.router"):
        _telegram_verification_error(failure, None)

    assert _UNREACHABLE in caplog.text
    assert token not in caplog.text
