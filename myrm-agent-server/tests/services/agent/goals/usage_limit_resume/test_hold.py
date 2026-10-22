"""on_goal_hold: stamp, arm and notify for a parked goal; only notify for a paused one."""

from __future__ import annotations

from myrm_agent_harness.agent.goals.types import GoalStatus
from myrm_agent_harness.agent.goals.wait_provider_window import park_goal_for_provider_window
from myrm_agent_harness.api.hooks import GOAL_WAIT_KIND_KEY

from app.services.agent.goals.usage_limit_resume import daemon as daemon_module
from app.services.agent.goals.usage_limit_resume import hold as hold_module
from app.services.agent.goals.usage_limit_resume.daemon import WAKE_OWNER, WAKE_OWNER_KEY, UsageLimitWakeDaemon
from app.services.agent.goals.usage_limit_resume.hold import build_goal_hold_callback

from .conftest import SESSION, window_hint


async def test_parked_goal_is_stamped_armed_and_announced(manager, clock, effects, monkeypatch) -> None:
    fresh = UsageLimitWakeDaemon(clock=clock)
    monkeypatch.setattr(daemon_module, "_daemon", fresh)
    monkeypatch.setattr(hold_module, "get_usage_limit_wake_daemon", lambda: fresh)
    await manager.create_goal(SESSION, "ship it")
    hint = window_hint(clock, 3600)
    parked = await park_goal_for_provider_window(manager, SESSION, hint)
    assert parked is not None

    await build_goal_hold_callback()(parked, hint)

    stamped = await manager.get_goal(parked.goal_id)
    assert stamped is not None
    assert stamped.status is GoalStatus.WAIT
    assert stamped.metadata[WAKE_OWNER_KEY] == WAKE_OWNER
    assert stamped.metadata[GOAL_WAIT_KIND_KEY] == "usage_limit"
    assert SESSION in fresh._armed
    assert effects.notices == [(SESSION, "wait")]


async def test_paused_goal_is_only_announced(manager, clock, effects, monkeypatch) -> None:
    fresh = UsageLimitWakeDaemon(clock=clock)
    monkeypatch.setattr(hold_module, "get_usage_limit_wake_daemon", lambda: fresh)
    await manager.create_goal(SESSION, "ship it")
    hint = window_hint(clock, 3 * 86_400)
    paused = await park_goal_for_provider_window(manager, SESSION, hint)
    assert paused is not None
    assert paused.status is GoalStatus.PAUSED

    await build_goal_hold_callback()(paused, hint)

    untouched = await manager.get_goal(paused.goal_id)
    assert untouched is not None
    assert WAKE_OWNER_KEY not in untouched.metadata
    assert fresh._armed == {}
    assert effects.notices == [(SESSION, "paused")]
