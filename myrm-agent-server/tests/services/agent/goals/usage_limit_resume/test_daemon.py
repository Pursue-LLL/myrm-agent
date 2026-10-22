"""Wake daemon against a real GoalManager: due goals resume, everything else is left alone."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest
from myrm_agent_harness.agent.goals.types import GoalStatus
from myrm_agent_harness.agent.goals.wait_provider_window import park_goal_for_provider_window
from myrm_agent_harness.api.hooks import GOAL_WAIT_KIND_KEY, GOAL_WAIT_RESUME_AT_KEY

from app.services.agent.goals.usage_limit_resume import daemon as daemon_module
from app.services.agent.goals.usage_limit_resume.daemon import (
    _BUSY_RETRY_S,
    _ERROR_RETRY_S,
    _MAX_WAKE_ERRORS,
    _STARTUP_GRACE_S,
    _WAKE_MARGIN_S,
    ResumeResult,
    UsageLimitWakeDaemon,
    resume_goal_after_usage_limit,
)

from .conftest import NOW, SESSION, FakeClock, park_owned_goal, window_hint

_DAY = 86_400


async def test_due_goal_leaves_wait_and_runs_an_unattended_turn(manager, daemon, clock, effects) -> None:
    goal = await park_owned_goal(manager, clock, wait_s=600)
    daemon.arm(SESSION, NOW + 600)
    clock.now = NOW + 600 + _WAKE_MARGIN_S

    await daemon._wake_due()

    resumed = await manager.get_goal(goal.goal_id)
    assert resumed is not None
    assert resumed.status is GoalStatus.ACTIVE
    assert GOAL_WAIT_KIND_KEY not in resumed.metadata
    effects.trigger.assert_awaited_once()
    assert effects.trigger.await_args.args[0] == SESSION
    assert effects.trigger.await_args.kwargs["on_failure"] == "needs_human_review"
    assert effects.notices == [(SESSION, "resumed")]
    assert daemon._armed == {}


async def test_goal_is_not_touched_before_the_window_reopens(manager, daemon, clock, effects) -> None:
    goal = await park_owned_goal(manager, clock, wait_s=600)
    daemon.arm(SESSION, NOW + 600)
    clock.now = NOW + 599

    await daemon._wake_due()

    parked = await manager.get_goal(goal.goal_id)
    assert parked is not None
    assert parked.status is GoalStatus.WAIT
    effects.trigger.assert_not_awaited()
    assert SESSION in daemon._armed


async def test_next_due_at_is_the_earliest_armed_wake_after_the_cutoff_and_follows_disarm(daemon) -> None:
    assert daemon.next_due_at(NOW) is None

    daemon.arm("late", NOW + 900)
    daemon.arm("early", NOW + 300)
    assert daemon.next_due_at(NOW) == NOW + 300 + _WAKE_MARGIN_S

    daemon.disarm("early")
    assert daemon.next_due_at(NOW) == NOW + 900 + _WAKE_MARGIN_S

    daemon.disarm("late")
    assert daemon.next_due_at(NOW) is None


async def test_next_due_at_skips_overdue_entries_instead_of_hiding_later_ones(daemon) -> None:
    daemon.arm("overdue", NOW - 600)
    daemon.arm("upcoming", NOW + 600)

    assert daemon.next_due_at(NOW) == NOW + 600 + _WAKE_MARGIN_S


async def test_wake_waits_for_the_provider_clock_margin(manager, daemon, clock, effects) -> None:
    await park_owned_goal(manager, clock, wait_s=600)
    daemon.arm(SESSION, NOW + 600)
    clock.now = NOW + 600  # reset second reached, margin not yet

    await daemon._wake_due()

    effects.trigger.assert_not_awaited()


async def test_busy_session_is_retried_not_resumed(manager, daemon, clock, effects) -> None:
    goal = await park_owned_goal(manager, clock)
    daemon.arm(SESSION, NOW + 600)
    clock.now = NOW + 700
    effects.active_sessions.add(SESSION)

    await daemon._wake_due()

    parked = await manager.get_goal(goal.goal_id)
    assert parked is not None
    assert parked.status is GoalStatus.WAIT
    effects.trigger.assert_not_awaited()
    assert daemon._armed[SESSION] == clock.now + _BUSY_RETRY_S


async def test_draining_gateway_defers_every_wake(manager, daemon, clock, effects) -> None:
    await park_owned_goal(manager, clock)
    daemon.arm(SESSION, NOW + 600)
    clock.now = NOW + 700
    effects.draining = True

    await daemon._wake_due()

    effects.trigger.assert_not_awaited()
    assert SESSION in daemon._armed


async def test_wake_far_after_the_window_pauses_for_the_user(manager, daemon, clock, effects) -> None:
    goal = await park_owned_goal(manager, clock)
    daemon.arm(SESSION, NOW + 600)
    clock.now = NOW + 600 + _DAY + 1

    await daemon._wake_due()

    paused = await manager.get_goal(goal.goal_id)
    assert paused is not None
    assert paused.status is GoalStatus.PAUSED
    effects.trigger.assert_not_awaited()
    assert effects.notices == [(SESSION, "paused")]
    assert daemon._armed == {}


@pytest.mark.parametrize("settle", ["pause", "cancel"])
async def test_goal_the_user_already_settled_is_dropped(manager, daemon, clock, effects, settle) -> None:
    goal = await park_owned_goal(manager, clock)
    await manager.update_status(goal.goal_id, GoalStatus.PAUSED if settle == "pause" else GoalStatus.CANCELLED)
    daemon.arm(SESSION, NOW + 600)
    clock.now = NOW + 700

    await daemon._wake_due()

    effects.trigger.assert_not_awaited()
    assert daemon._armed == {}


async def test_goal_without_the_ownership_stamp_is_never_woken(manager, daemon, clock, effects) -> None:
    await manager.create_goal(SESSION, "kanban owned")
    await park_goal_for_provider_window(manager, SESSION, window_hint(clock, 600))
    daemon.arm(SESSION, NOW + 600)
    clock.now = NOW + 700

    await daemon._wake_due()

    effects.trigger.assert_not_awaited()
    assert daemon._armed == {}


async def test_stream_that_parks_the_goal_again_keeps_its_new_arm(manager, daemon, clock, effects) -> None:
    await park_owned_goal(manager, clock)
    daemon.arm(SESSION, NOW + 600)
    clock.now = NOW + 700

    async def trigger_then_rearm(*_args: object, **_kwargs: object) -> bool:
        daemon.arm(SESSION, NOW + 5000)
        return True

    effects.trigger.side_effect = trigger_then_rearm

    await daemon._wake_due()

    assert daemon._armed[SESSION] == NOW + 5000 + _WAKE_MARGIN_S


async def test_wake_errors_retry_then_give_up(manager, daemon, clock, effects, monkeypatch) -> None:
    daemon.arm(SESSION, NOW)
    monkeypatch.setattr(daemon, "_wake", AsyncMock(side_effect=OSError("disk")))

    for attempt in range(1, _MAX_WAKE_ERRORS):
        clock.now = NOW + 1000 * attempt
        await daemon._wake_due()
        assert daemon._armed[SESSION] == clock.now + _ERROR_RETRY_S

    clock.now += 1000
    await daemon._wake_due()

    assert daemon._armed == {}


async def test_rebuild_arms_only_owned_waiting_goals_after_the_startup_grace(
    manager, daemon, clock, effects, storage, monkeypatch
) -> None:
    monkeypatch.setattr("myrm_agent_harness.toolkits.storage.factory.get_storage_provider", lambda: storage)
    await park_owned_goal(manager, clock, wait_s=60)
    await manager.create_goal("chat-2", "plain active goal")
    clock.now = NOW + 3600  # the window reopened while the server was down

    await daemon._rebuild()

    assert daemon._armed == {SESSION: clock.now + _STARTUP_GRACE_S}


async def test_manual_retry_resumes_before_the_reset_and_disarms(manager, clock, effects, monkeypatch) -> None:
    goal = await park_owned_goal(manager, clock, wait_s=3600)
    fresh = UsageLimitWakeDaemon(clock=clock)
    monkeypatch.setattr(daemon_module, "_daemon", fresh)
    fresh.arm(SESSION, NOW + 3600)

    result = await resume_goal_after_usage_limit(SESSION)

    assert result is ResumeResult.RESUMED
    resumed = await manager.get_goal(goal.goal_id)
    assert resumed is not None
    assert resumed.status is GoalStatus.ACTIVE
    assert GOAL_WAIT_RESUME_AT_KEY not in resumed.metadata
    effects.trigger.assert_awaited_once()
    assert fresh._armed == {}


async def test_manual_retry_reports_busy_without_leaving_wait(manager, clock, effects) -> None:
    goal = await park_owned_goal(manager, clock)
    effects.active_sessions.add(SESSION)

    result = await resume_goal_after_usage_limit(SESSION)

    assert result is ResumeResult.BUSY
    parked = await manager.get_goal(goal.goal_id)
    assert parked is not None
    assert parked.status is GoalStatus.WAIT


async def test_manual_retry_without_a_usage_limit_wait_is_refused(manager, effects) -> None:
    await manager.create_goal(SESSION, "plain")

    assert await resume_goal_after_usage_limit(SESSION) is ResumeResult.NOT_WAITING
    effects.trigger.assert_not_awaited()


async def test_loop_wakes_an_armed_goal_and_goes_idle_again(manager, clock, effects, monkeypatch) -> None:
    await park_owned_goal(manager, clock)
    clock.now = NOW + 700
    loop_daemon = UsageLimitWakeDaemon(clock=clock)
    monkeypatch.setattr(loop_daemon, "_rebuild", AsyncMock())
    resumed = asyncio.Event()

    async def signal_resumed(*_args: object, **_kwargs: object) -> bool:
        resumed.set()
        return True

    effects.trigger.side_effect = signal_resumed

    await loop_daemon.start()
    try:
        await asyncio.sleep(0)  # idle: nothing armed, nothing happens
        effects.trigger.assert_not_awaited()
        loop_daemon.arm(SESSION, NOW + 600)
        await asyncio.wait_for(resumed.wait(), timeout=5)
        await asyncio.sleep(0.05)
        assert loop_daemon._armed == {}
    finally:
        await loop_daemon.stop()
    assert loop_daemon._task is None


async def test_start_is_idempotent_and_stop_is_safe_when_never_started() -> None:
    idle = UsageLimitWakeDaemon(clock=FakeClock())
    await idle.stop()
    idle._rebuild = AsyncMock()  # type: ignore[method-assign]

    await idle.start()
    first = idle._task
    await idle.start()

    assert idle._task is first
    await idle.stop()
