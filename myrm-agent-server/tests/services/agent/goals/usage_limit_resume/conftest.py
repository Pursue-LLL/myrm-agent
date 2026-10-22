"""Shared fixtures: a real GoalManager on temp storage, a fake clock, and recorded side effects."""

from __future__ import annotations

from dataclasses import dataclass, field
from unittest.mock import AsyncMock

import pytest
from myrm_agent_harness.agent.goals.manager import GoalManager
from myrm_agent_harness.agent.goals.types import Goal
from myrm_agent_harness.agent.goals.wait_provider_window import park_goal_for_provider_window
from myrm_agent_harness.toolkits.llms.errors.provider_window import ProviderWindowHint, WindowSource
from myrm_agent_harness.toolkits.storage.local import LocalStorageBackend

from app.services.agent.goals.usage_limit_resume import daemon as daemon_module
from app.services.agent.goals.usage_limit_resume import hold as hold_module
from app.services.agent.goals.usage_limit_resume.daemon import WAKE_OWNER, WAKE_OWNER_KEY, UsageLimitWakeDaemon

SESSION = "chat-1"
NOW = 1_800_000_000.0


class FakeClock:
    def __init__(self, now: float = NOW) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


@dataclass
class Effects:
    """What the daemon did to the outside world."""

    notices: list[tuple[str, str]] = field(default_factory=list)
    active_sessions: set[str] = field(default_factory=set)
    draining: bool = False
    trigger: AsyncMock = field(default_factory=lambda: AsyncMock(return_value=True))


class _FakeGateway:
    def __init__(self, effects: Effects) -> None:
        self._effects = effects

    @property
    def is_draining(self) -> bool:
        return self._effects.draining

    def is_session_active(self, session_id: str) -> bool:
        return session_id in self._effects.active_sessions


@pytest.fixture
def storage(tmp_path) -> LocalStorageBackend:
    return LocalStorageBackend(base_path=str(tmp_path))


@pytest.fixture
def manager(storage, monkeypatch) -> GoalManager:
    goal_manager = GoalManager(storage)
    monkeypatch.setattr(daemon_module.GoalRegistry, "get_or_create_provider", lambda session_id: goal_manager)
    return goal_manager


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def effects(monkeypatch) -> Effects:
    recorded = Effects()

    async def notify(session_id: str, goal_id: str, notice: str) -> None:
        recorded.notices.append((session_id, notice))

    monkeypatch.setattr(daemon_module, "get_agent_gateway", lambda: _FakeGateway(recorded))
    monkeypatch.setattr(daemon_module, "trigger_goal_stream_with_failure_policy", recorded.trigger)
    monkeypatch.setattr(daemon_module, "publish_goal_usage_limit_notification", notify)
    monkeypatch.setattr(hold_module, "publish_goal_usage_limit_notification", notify)
    return recorded


@pytest.fixture
def daemon(clock, manager, effects) -> UsageLimitWakeDaemon:
    return UsageLimitWakeDaemon(clock=clock)


def window_hint(clock: FakeClock, wait_s: float) -> ProviderWindowHint:
    return ProviderWindowHint(
        reset_at=clock.now + wait_s, wait_s=wait_s, source=WindowSource.ANTHROPIC_UNIFIED, quota_window=True
    )


async def park_owned_goal(manager: GoalManager, clock: FakeClock, wait_s: float = 600) -> Goal:
    """A goal parked exactly the way the hold callback leaves it."""
    await manager.create_goal(SESSION, "ship it")
    parked = await park_goal_for_provider_window(manager, SESSION, window_hint(clock, wait_s))
    assert parked is not None
    return await manager.update_metadata(parked.goal_id, {WAKE_OWNER_KEY: WAKE_OWNER})
