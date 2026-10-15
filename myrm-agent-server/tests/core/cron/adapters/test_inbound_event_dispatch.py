"""Tests for inbound channel → cron event dispatch helper."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from myrm_agent_harness.api.security import is_untrusted_ingress_active

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

    count = await dispatch_cron_event_for_inbound_message("   ", "feishu", "user-1", untrusted=False)

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
        untrusted=False,
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

    count = await dispatch_cron_event_for_inbound_message("alert", "telegram", "u1", untrusted=False)

    assert count == 0


class _SpawningScheduler:
    """Stands in for CronScheduler: like ``dispatch_event`` it spawns the job task and returns before it runs."""

    def __init__(self) -> None:
        self.seen_by_job: list[bool] = []
        self.jobs: list[asyncio.Task[None]] = []

    async def dispatch_event(self, message: str, channel: str, user_id: str) -> int:
        async def job() -> None:
            await asyncio.sleep(0)
            self.seen_by_job.append(is_untrusted_ingress_active())

        self.jobs.append(asyncio.create_task(job()))
        return 1


@pytest.mark.asyncio
@pytest.mark.parametrize(("untrusted", "job_is_fenced"), [(True, True), (False, False)])
async def test_job_task_inherits_the_fence_only_for_an_untrusted_sender(
    monkeypatch: pytest.MonkeyPatch, untrusted: bool, job_is_fenced: bool
) -> None:
    scheduler = _SpawningScheduler()
    monkeypatch.setattr("app.core.cron.adapters.setup.get_cron_scheduler", lambda: scheduler)

    count = await dispatch_cron_event_for_inbound_message("alert", "feishu", "u1", untrusted=untrusted)
    await asyncio.gather(*scheduler.jobs)

    assert count == 1
    assert scheduler.seen_by_job == [job_is_fenced]
    assert not is_untrusted_ingress_active()


@pytest.mark.asyncio
async def test_fence_does_not_leak_into_the_dispatcher_when_the_scheduler_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    scheduler = AsyncMock()
    scheduler.dispatch_event = AsyncMock(side_effect=RuntimeError("scheduler down"))
    monkeypatch.setattr("app.core.cron.adapters.setup.get_cron_scheduler", lambda: scheduler)

    count = await dispatch_cron_event_for_inbound_message("alert", "feishu", "u1", untrusted=True)

    assert count == 0
    assert not is_untrusted_ingress_active()
