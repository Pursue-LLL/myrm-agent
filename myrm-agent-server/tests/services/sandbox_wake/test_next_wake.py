"""earliest_scheduled_wake: min of parked-goal wake time, next cron run and next kanban release, future only."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.sandbox_wake.next_wake import _WAKE_LEAD_S, earliest_scheduled_wake

_NOW = 1_000_000.0
_MODULE = "app.services.sandbox_wake.next_wake"


def _utc(epoch: float) -> datetime:
    return datetime.fromtimestamp(epoch, tz=timezone.utc)


def _patch_sources(*, goal_due: float | None, cron_due: float | None, kanban_due: float | None):
    daemon = MagicMock()
    daemon.next_due_at.side_effect = lambda after: goal_due if goal_due is not None and goal_due > after else None
    cron_store = MagicMock()
    cron_store.earliest_next_run = AsyncMock(return_value=None if cron_due is None else _utc(cron_due))
    kanban_store = MagicMock()
    kanban_store.earliest_scheduled_until = AsyncMock(
        side_effect=lambda after: _utc(kanban_due) if kanban_due is not None and _utc(kanban_due) > after else None
    )
    service = MagicMock(store=kanban_store)
    return (
        patch(f"{_MODULE}.get_usage_limit_wake_daemon", return_value=daemon),
        patch(f"{_MODULE}.get_cron_store", return_value=cron_store),
        patch(f"{_MODULE}.KanbanService.get_instance", return_value=service),
    ), kanban_store


async def _earliest(
    *, goal_due: float | None = None, cron_due: float | None = None, kanban_due: float | None = None
) -> float | None:
    (goal_patch, cron_patch, kanban_patch), _ = _patch_sources(goal_due=goal_due, cron_due=cron_due, kanban_due=kanban_due)
    with goal_patch, cron_patch, kanban_patch:
        return await earliest_scheduled_wake(_NOW)


@pytest.mark.asyncio
async def test_nothing_scheduled() -> None:
    assert await _earliest() is None


@pytest.mark.asyncio
async def test_earliest_of_the_three_sources_wins() -> None:
    assert await _earliest(goal_due=_NOW + 900, cron_due=_NOW + 600, kanban_due=_NOW + 1200) == _NOW + 600 - _WAKE_LEAD_S
    assert await _earliest(goal_due=_NOW + 900, cron_due=_NOW + 1200, kanban_due=_NOW + 300) == _NOW + 300
    assert await _earliest(goal_due=_NOW + 300, cron_due=_NOW + 600, kanban_due=_NOW + 900) == _NOW + 300 - _WAKE_LEAD_S


@pytest.mark.asyncio
async def test_timer_driven_sources_are_reported_early() -> None:
    assert await _earliest(goal_due=_NOW + 900) == _NOW + 900 - _WAKE_LEAD_S
    assert await _earliest(cron_due=_NOW + 300) == _NOW + 300 - _WAKE_LEAD_S


@pytest.mark.asyncio
async def test_kanban_release_is_reported_at_its_due_time_not_early() -> None:
    """A poll that expired while paused runs on resume; waking early would make that first poll miss the task."""
    assert await _earliest(kanban_due=_NOW + 1200) == _NOW + 1200


@pytest.mark.asyncio
async def test_past_times_are_ignored() -> None:
    assert await _earliest(goal_due=_NOW - 5) is None
    assert await _earliest(goal_due=_NOW, cron_due=_NOW - 60) is None
    assert await _earliest(goal_due=_NOW - 5, cron_due=_NOW + 300) == _NOW + 300 - _WAKE_LEAD_S
    assert await _earliest(kanban_due=_NOW - 5, cron_due=_NOW + 300) == _NOW + 300 - _WAKE_LEAD_S


@pytest.mark.asyncio
async def test_due_time_within_the_lead_window_is_reported_as_is() -> None:
    assert await _earliest(cron_due=_NOW + _WAKE_LEAD_S) == _NOW + _WAKE_LEAD_S
    assert await _earliest(goal_due=_NOW + 20) == _NOW + 20


@pytest.mark.asyncio
async def test_kanban_is_asked_only_for_times_after_now() -> None:
    """The store query is bounded by ``now`` so an overdue task cannot hide a later one."""
    sources, kanban_store = _patch_sources(goal_due=None, cron_due=None, kanban_due=_NOW + 300)
    with sources[0], sources[1], sources[2]:
        await earliest_scheduled_wake(_NOW)

    kanban_store.earliest_scheduled_until.assert_awaited_once_with(_utc(_NOW))
