"""Tests for Telegram onboarding orchestration endpoint."""

from __future__ import annotations

import asyncio
import os
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


@asynccontextmanager
async def _noop_lifespan(_app: object):
    yield


def _cleanup_db_files() -> None:
    TEST_DB.unlink(missing_ok=True)
    for suffix in ("-shm", "-wal", "-journal"):
        Path(f"{TEST_DB}{suffix}").unlink(missing_ok=True)


def _put_config(client: TestClient, key: str, value: dict[str, object]) -> None:
    response = client.put(
        f"/api/v1/config/{key}",
        json={
            "value": value,
            "deviceId": "test-suite",
        },
    )
    assert response.status_code == 200


def _get_config_value(client: TestClient, key: str) -> dict[str, object]:
    response = client.get(f"/api/v1/config/{key}")
    assert response.status_code == 200
    payload = response.json()
    value = payload.get("value")
    assert isinstance(value, dict)
    return value


@pytest.fixture(scope="module", autouse=True)
def setup_test_database():
    asyncio.run(init_database())
    yield
    _cleanup_db_files()


def test_apply_telegram_onboarding_success() -> None:
    original_lifespan = app.router.lifespan_context
    app.router.lifespan_context = _noop_lifespan
    try:
        with (
            patch("app.core.security.auth.identity.is_loopback_ip", return_value=True),
            patch("app.api.config.router._verify_telegram_token", new=AsyncMock(return_value="myrm_bot")),
            patch("app.api.config.router._try_hot_register_channel", new=AsyncMock()),
            patch("app.api.config.router._wait_for_telegram_channel_state", new=AsyncMock(return_value=(True, "running"))),
            patch("app.core.channel_bridge.setup.refresh_reaction_policy", new=AsyncMock()),
            patch("app.core.channel_bridge.topic_config.SqlTopicManager.bind_topic", new=AsyncMock()),
            patch("app.services.agent.agent_service.AgentService.get_agents_by_name", new=AsyncMock(return_value=[])),
            patch(
                "app.services.agent.agent_service.AgentService.create_agent",
                new=AsyncMock(
                    return_value=SimpleNamespace(
                        id="agent-telegram-1",
                        display_name="My Telegram Assistant",
                    )
                ),
            ),
            TestClient(app, base_url="http://127.0.0.1", raise_server_exceptions=False) as client,
        ):
            _put_config(
                client,
                "telegramCredentials",
                {
                    "botToken": "old-token",
                    "enabled": True,
                    "botPolicy": "mention_only",
                    "webhookUrl": "https://legacy.example.com/webhook",
                },
            )

            response = client.post(
                "/api/v1/config/onboarding/telegram-assistant/apply",
                json={
                    "botToken": "1234567890:VALID_TOKEN",
                    "assistantName": "My Telegram Assistant",
                    "assistantDescription": "Personal helper",
                },
            )
            assert response.status_code == 200
            payload = response.json()
            assert payload["success"] is True
            assert payload["botUsername"] == "myrm_bot"
            assert payload["agentId"] == "agent-telegram-1"
            assert payload["channelEnabled"] is True
            assert payload["connected"] is True
            assert payload["status"] == "running"

            telegram_creds = _get_config_value(client, "telegramCredentials")
            assert telegram_creds["botToken"] == "1234567890:VALID_TOKEN"
            assert telegram_creds["enabled"] is True
            assert telegram_creds["botPolicy"] == "mention_only"
            assert telegram_creds["webhookUrl"] == ""

            channels_cfg = _get_config_value(client, "channels")
            channels = channels_cfg.get("channels")
            assert isinstance(channels, dict)
            telegram_cfg = channels.get("telegram")
            assert isinstance(telegram_cfg, dict)
            assert telegram_cfg["dmPolicy"] == "open"
    finally:
        app.router.lifespan_context = original_lifespan


def test_apply_telegram_onboarding_rolls_back_on_failure() -> None:
    original_lifespan = app.router.lifespan_context
    app.router.lifespan_context = _noop_lifespan
    try:
        with (
            patch("app.core.security.auth.identity.is_loopback_ip", return_value=True),
            patch("app.api.config.router._verify_telegram_token", new=AsyncMock(return_value="myrm_bot")),
            patch("app.api.config.router._try_hot_register_channel", new=AsyncMock()),
            patch("app.core.channel_bridge.setup.refresh_reaction_policy", new=AsyncMock()),
            patch(
                "app.core.channel_bridge.topic_config.SqlTopicManager.bind_topic",
                new=AsyncMock(side_effect=RuntimeError("bind failed")),
            ),
            patch("app.services.agent.agent_service.AgentService.get_agents_by_name", new=AsyncMock(return_value=[])),
            patch(
                "app.services.agent.agent_service.AgentService.create_agent",
                new=AsyncMock(
                    return_value=SimpleNamespace(
                        id="agent-rollback-1",
                        display_name="Rollback Assistant",
                    )
                ),
            ),
            patch("app.services.agent.agent_service.AgentService.delete_agent", new=AsyncMock(return_value=True)) as delete_agent_mock,
            TestClient(app, base_url="http://127.0.0.1", raise_server_exceptions=False) as client,
        ):
            _put_config(
                client,
                "telegramCredentials",
                {
                    "botToken": "old-token",
                    "enabled": False,
                    "botPolicy": "deny",
                },
            )
            _put_config(
                client,
                "channels",
                {
                    "dmPolicy": "allowlist",
                },
            )

            response = client.post(
                "/api/v1/config/onboarding/telegram-assistant/apply",
                json={
                    "botToken": "9999999999:NEW_TOKEN",
                    "assistantName": "Rollback Assistant",
                },
            )
            assert response.status_code == 500
            assert response.json()["detail"] == "Failed to apply Telegram onboarding package"

            restored_creds = _get_config_value(client, "telegramCredentials")
            assert restored_creds["botToken"] == "old-token"
            assert restored_creds["enabled"] is False
            assert restored_creds["botPolicy"] == "deny"

            restored_channels = _get_config_value(client, "channels")
            assert restored_channels["dmPolicy"] == "allowlist"
            delete_agent_mock.assert_awaited_once_with("agent-rollback-1")
    finally:
        app.router.lifespan_context = original_lifespan


def test_apply_telegram_onboarding_reuses_existing_general_agent_after_search_name_conflict() -> None:
    original_lifespan = app.router.lifespan_context
    app.router.lifespan_context = _noop_lifespan
    try:
        with (
            patch("app.core.security.auth.identity.is_loopback_ip", return_value=True),
            patch("app.api.config.router._verify_telegram_token", new=AsyncMock(return_value="myrm_bot")),
            patch("app.api.config.router._try_hot_register_channel", new=AsyncMock()),
            patch("app.api.config.router._wait_for_telegram_channel_state", new=AsyncMock(return_value=(True, "running"))),
            patch("app.core.channel_bridge.setup.refresh_reaction_policy", new=AsyncMock()),
            patch("app.core.channel_bridge.topic_config.SqlTopicManager.bind_topic", new=AsyncMock()),
            patch(
                "app.services.agent.agent_service.AgentService.get_agents_by_name",
                new=AsyncMock(
                    side_effect=[
                        [
                            SimpleNamespace(
                                id="agent-search-1",
                                display_name="My Telegram Assistant",
                                metadata={"prompt_mode": "search"},
                            )
                        ],
                        [
                            SimpleNamespace(
                                id="agent-general-1",
                                display_name="My Telegram Assistant (General)",
                                metadata={"prompt_mode": "full"},
                            )
                        ],
                    ]
                ),
            ),
            patch("app.services.agent.agent_service.AgentService.create_agent", new=AsyncMock()) as create_agent_mock,
            TestClient(app, base_url="http://127.0.0.1", raise_server_exceptions=False) as client,
        ):
            response = client.post(
                "/api/v1/config/onboarding/telegram-assistant/apply",
                json={
                    "botToken": "1234567890:VALID_TOKEN",
                    "assistantName": "My Telegram Assistant",
                },
            )
            assert response.status_code == 200
            payload = response.json()
            assert payload["success"] is True
            assert payload["agentId"] == "agent-general-1"
            assert payload["agentName"] == "My Telegram Assistant (General)"
            create_agent_mock.assert_not_awaited()
    finally:
        app.router.lifespan_context = original_lifespan


@pytest.mark.asyncio
async def test_resolve_or_create_telegram_agent_avoids_duplicate_create_under_concurrency() -> None:
    from app.api.config.router import (
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
    import app.api.config.router as config_router

    request = config_router.TelegramAssistantOnboardingRequest(
        botToken="1234567890:VALID_TOKEN",
        assistantName="Busy Assistant",
    )
    lock_path = config_router._telegram_agent_cross_process_lock_path(
        request.assistant_name
    )
    busy_lock = FileLock(str(lock_path))
    busy_lock.acquire(timeout=0)
    monkeypatch.setattr(
        config_router,
        "_TELEGRAM_AGENT_CROSS_PROCESS_LOCK_TIMEOUT_SEC",
        0.0,
    )

    try:
        with patch(
            "app.services.agent.agent_service.AgentService.get_agents_by_name",
            new=AsyncMock(return_value=[]),
        ) as get_agents_mock:
            with pytest.raises(HTTPException) as exc_info:
                await config_router._resolve_or_create_telegram_agent(request)
    finally:
        if busy_lock.is_locked:
            busy_lock.release()

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == {
        "code": "TELEGRAM_ONBOARDING_IN_PROGRESS",
        "message": "Telegram onboarding is already in progress. Please retry shortly.",
    }
    get_agents_mock.assert_not_awaited()
