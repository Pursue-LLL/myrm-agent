"""Resolving the onboarding assistant under contention: a busy or invalid request is answered as such and changes nothing."""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from filelock import FileLock

from app.database.connection import init_database
from tests.support.minimal_app import build_minimal_app

TEST_WS = Path(os.environ["MYRM_DATA_DIR"])
TEST_DB = TEST_WS / "data.db"

app = build_minimal_app(preset="config")

_APPLY_URL = "/api/v1/config/onboarding/telegram-assistant/apply"
_IN_PROGRESS_DETAIL = {
    "code": "TELEGRAM_ONBOARDING_IN_PROGRESS",
    "message": "Telegram onboarding is already in progress. Please retry shortly.",
}
_SAVED_CREDENTIALS = {"botToken": "old-token", "enabled": False, "botPolicy": "deny"}


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
def rollback() -> Iterator[AsyncMock]:
    with patch("app.api.config.telegram_onboarding._rollback_telegram_onboarding", new=AsyncMock()) as mock:
        yield mock


@pytest.fixture
def client(rollback: AsyncMock) -> Iterator[TestClient]:
    original_lifespan = app.router.lifespan_context
    app.router.lifespan_context = _noop_lifespan
    try:
        with (
            patch("app.core.security.auth.identity.is_loopback_ip", return_value=True),
            patch("app.api.config.telegram_onboarding._verify_telegram_token", new=AsyncMock(return_value="myrm_bot")),
            patch("app.services.channels.credential_reload.reload_channel_credentials", new=AsyncMock()),
            TestClient(app, base_url="http://127.0.0.1", raise_server_exceptions=False) as test_client,
        ):
            response = test_client.put(
                "/api/v1/config/telegramCredentials",
                json={"value": _SAVED_CREDENTIALS, "deviceId": "test-suite"},
            )
            assert response.status_code == 200
            yield test_client
    finally:
        app.router.lifespan_context = original_lifespan


def _request(assistant_name: str) -> dict[str, str]:
    return {"botToken": "1234567890:VALID_TOKEN", "assistantName": assistant_name}


def _saved_bot_token(client: TestClient) -> object:
    return client.get("/api/v1/config/telegramCredentials").json()["value"]["botToken"]


def test_a_busy_onboarding_is_answered_409_and_the_saved_credentials_are_left_alone(
    client: TestClient, rollback: AsyncMock
) -> None:
    import app.api.config.telegram_onboarding as telegram_onboarding

    busy_lock = FileLock(str(telegram_onboarding._telegram_agent_cross_process_lock_path("Busy Assistant")))
    busy_lock.acquire(timeout=0)
    try:
        response = client.post(_APPLY_URL, json=_request("Busy Assistant"))
    finally:
        busy_lock.release()

    assert response.status_code == 409
    assert response.json()["detail"] == _IN_PROGRESS_DETAIL
    rollback.assert_not_awaited()
    assert _saved_bot_token(client) == "old-token"


def test_a_blank_assistant_name_is_answered_422_and_nothing_is_rolled_back(client: TestClient, rollback: AsyncMock) -> None:
    response = client.post(_APPLY_URL, json=_request("   "))

    assert response.status_code == 422
    assert response.json()["detail"] == "Assistant name is required"
    rollback.assert_not_awaited()
    assert _saved_bot_token(client) == "old-token"


@pytest.mark.asyncio
async def test_resolve_or_create_telegram_agent_avoids_duplicate_create_under_concurrency() -> None:
    from app.api.config.telegram_onboarding import (
        TelegramAssistantOnboardingRequest,
        _resolve_or_create_telegram_agent,
    )

    requested_name = "Concurrent Assistant"
    created_profile = SimpleNamespace(
        id="agent-concurrent-1",
        display_name=requested_name,
        metadata={"prompt_mode": "full"},
    )
    created_once = False
    create_calls = 0

    async def _fake_get_agents_by_name(name: str) -> list[SimpleNamespace]:
        if name == requested_name and created_once:
            return [created_profile]
        return []

    async def _fake_create_agent(*_args: object, **_kwargs: object) -> SimpleNamespace:
        nonlocal created_once, create_calls
        create_calls += 1
        await asyncio.sleep(0.05)
        created_once = True
        return created_profile

    with (
        patch(
            "app.services.agent.agent_service.AgentService.get_agents_by_name",
            new=AsyncMock(side_effect=_fake_get_agents_by_name),
        ),
        patch(
            "app.services.agent.agent_service.AgentService.create_agent",
            new=AsyncMock(side_effect=_fake_create_agent),
        ),
    ):
        request = TelegramAssistantOnboardingRequest(
            botToken="1234567890:VALID_TOKEN",
            assistantName=requested_name,
        )
        first, second = await asyncio.gather(
            _resolve_or_create_telegram_agent(request),
            _resolve_or_create_telegram_agent(request),
        )

    assert first[0] == "agent-concurrent-1"
    assert second[0] == "agent-concurrent-1"
    assert create_calls == 1


@pytest.mark.asyncio
async def test_resolve_or_create_telegram_agent_returns_conflict_when_cross_process_lock_busy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.api.config.telegram_onboarding as telegram_onboarding

    request = telegram_onboarding.TelegramAssistantOnboardingRequest(
        botToken="1234567890:VALID_TOKEN",
        assistantName="Busy Assistant",
    )
    lock_path = telegram_onboarding._telegram_agent_cross_process_lock_path(request.assistant_name)
    busy_lock = FileLock(str(lock_path))
    busy_lock.acquire(timeout=0)
    monkeypatch.setattr(
        telegram_onboarding,
        "_TELEGRAM_AGENT_CROSS_PROCESS_LOCK_TIMEOUT_SEC",
        0.0,
    )

    try:
        with patch(
            "app.services.agent.agent_service.AgentService.get_agents_by_name",
            new=AsyncMock(return_value=[]),
        ) as get_agents_mock:
            with pytest.raises(HTTPException) as exc_info:
                await telegram_onboarding._resolve_or_create_telegram_agent(request)
    finally:
        if busy_lock.is_locked:
            busy_lock.release()

    assert exc_info.value.status_code == 409
    detail: object = exc_info.value.detail
    assert detail == {
        "code": "TELEGRAM_ONBOARDING_IN_PROGRESS",
        "message": "Telegram onboarding is already in progress. Please retry shortly.",
    }
    get_agents_mock.assert_not_awaited()
