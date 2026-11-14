"""Tests for the Feishu channel doctor."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.channels.providers.feishu.doctor import diagnose_feishu_channel


def _client(*, bot_open_id: str = "ou_fake_bot_id", token: str | Exception = "t-fake-token") -> MagicMock:
    client = MagicMock()
    client.ensure_token = AsyncMock(side_effect=token) if isinstance(token, Exception) else AsyncMock(return_value=token)
    client.bot_open_id = bot_open_id
    return client


@pytest.mark.asyncio
async def test_a_working_websocket_app_passes_every_check() -> None:
    report = await diagnose_feishu_channel(_client(), app_id="cli_12345", transport_mode="websocket")

    assert report.is_healthy is True
    assert report.app_id == "cli_12345"
    assert [(c.name, c.passed) for c in report.checks] == [
        ("tenant_access_token", True),
        ("bot_identity", True),
        ("transport_mode", True),
    ]
    assert report.recommendations == []


@pytest.mark.asyncio
async def test_a_token_failure_ends_the_diagnosis_with_the_credentials_hint() -> None:
    report = await diagnose_feishu_channel(_client(token=RuntimeError("invalid app secret")), app_id="cli_12345")

    assert report.is_healthy is False
    assert [(c.name, c.passed) for c in report.checks] == [("tenant_access_token", False)]
    assert report.recommendations == ["Verify App ID and App Secret in Feishu Open Platform."]


@pytest.mark.asyncio
async def test_an_unresolved_bot_identity_is_unhealthy() -> None:
    report = await diagnose_feishu_channel(_client(bot_open_id=""), app_id="cli_12345")

    assert report.is_healthy is False
    assert [c.name for c in report.checks if not c.passed] == ["bot_identity"]
    assert report.recommendations == ["Ensure Bot capability is enabled in Feishu App Developer Console."]


@pytest.mark.asyncio
async def test_webhook_mode_without_a_url_is_flagged_but_does_not_make_the_app_unhealthy() -> None:
    report = await diagnose_feishu_channel(_client(), app_id="cli_12345", transport_mode="webhook")

    assert report.is_healthy is True
    assert [c.name for c in report.checks if not c.passed] == ["webhook_reachability"]
    assert report.recommendations == ["Configure a valid public Webhook URL or switch to WebSocket transport mode."]
