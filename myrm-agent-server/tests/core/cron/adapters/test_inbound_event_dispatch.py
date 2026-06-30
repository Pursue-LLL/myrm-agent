"""Tests for inbound channel → cron event dispatch helper."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.cron.adapters.inbound_event_dispatch import (
    dispatch_cron_event_for_inbound_message,
)


@pytest.mark.asyncio
async def test_dispatch_skips_blank_message(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_get = MagicMock()
    monkeypatch.setattr(
        "app.core.cron.adapters.setup.get_cron_scheduler",
        mock_get,
    )

    count = await dispatch_cron_event_for_inbound_message("   ", "feishu", "user-1")

    assert count == 0
    mock_get.assert_not_called()


@pytest.mark.asyncio
async def test_dispatch_delegates_to_scheduler(monkeypatch: pytest.MonkeyPatch) -> None:
    scheduler = AsyncMock()
    scheduler.dispatch_event = AsyncMock(return_value=2)

    monkeypatch.setattr(
        "app.core.cron.adapters.setup.get_cron_scheduler",
        lambda: scheduler,
    )

    count = await dispatch_cron_event_for_inbound_message(
        "server down alert",
        "feishu",
        "owner-1",
    )

    assert count == 2
    scheduler.dispatch_event.assert_awaited_once_with(
        "server down alert",
        "feishu",
        "owner-1",
    )


@pytest.mark.asyncio
async def test_dispatch_swallows_scheduler_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    scheduler = AsyncMock()
    scheduler.dispatch_event = AsyncMock(side_effect=RuntimeError("scheduler down"))

    monkeypatch.setattr(
        "app.core.cron.adapters.setup.get_cron_scheduler",
        lambda: scheduler,
    )

    count = await dispatch_cron_event_for_inbound_message("alert", "telegram", "u1")

    assert count == 0
