"""Wake goals parked on a provider usage limit once its window reopens.

[INPUT]
- myrm_agent_harness.api.hooks::GOAL_WAIT_* / PROVIDER_WINDOW_HOLD_MAX_S / pause_goal_after_missed_wake (POS: parked-goal vocabulary)
- app.services.agent.goals.goal_registry::GoalRegistry (POS: session GoalProvider)
- app.services.agent.goals.goal_stream_trigger::trigger_goal_stream_with_failure_policy (POS: unattended headless stream)
- app.services.agent.gateway::get_agent_gateway (POS: in-flight session and drain state)
- app.services.agent.goals.usage_limit_resume.notify (POS: user notification)

[OUTPUT]
- WAKE_OWNER_KEY / WAKE_OWNER: ownership stamp that makes a parked goal eligible for the daemon
- UsageLimitWakeDaemon / get_usage_limit_wake_daemon (``next_due_at``: earliest armed wake time after a cutoff, read by the hosted wake-schedule reporter)
- ResumeResult / resume_goal_after_usage_limit: manual "retry now"

[POS]
Host half of provider-window recovery. The harness parks a goal in WAIT with ``wait_resume_at``;
this daemon holds an in-memory set of those goals, polls the wall clock (never a monotonic timer,
so a suspended laptop wakes late instead of never) and resumes each through the same unattended
stream path every other headless goal continuation uses. Storage is the source of truth: the set
is rebuilt from it at startup and every wake re-reads the goal before acting. Idle with no armed goal.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import Callable
from datetime import datetime
from enum import Enum

from myrm_agent_harness.agent.goals.protocols import GoalProvider
from myrm_agent_harness.agent.goals.types import Goal, GoalStatus
from myrm_agent_harness.api.hooks import (
    GOAL_WAIT_KIND_KEY,
    GOAL_WAIT_KIND_USAGE_LIMIT,
    GOAL_WAIT_RESUME_AT_KEY,
    PROVIDER_WINDOW_HOLD_MAX_S,
    pause_goal_after_missed_wake,
)

from app.services.agent.gateway import get_agent_gateway
from app.services.agent.goals.goal_registry import GoalRegistry
from app.services.agent.goals.goal_stream_trigger import trigger_goal_stream_with_failure_policy
from app.services.agent.goals.usage_limit_resume.notify import publish_goal_usage_limit_notification

logger = logging.getLogger(__name__)

WAKE_OWNER_KEY = "wake_owner"
WAKE_OWNER = "usage_limit_wake_daemon"

_POLL_MAX_S = 30.0
_POLL_MIN_S = 1.0
# The provider's clock and ours differ by a second or two; waking early only burns a turn on a fresh rejection.
_WAKE_MARGIN_S = 2.0
_BUSY_RETRY_S = 15.0
_ERROR_RETRY_S = 60.0
_MAX_WAKE_ERRORS = 5
# Goals found already due at startup wait for the server to finish booting.
_STARTUP_GRACE_S = 15.0


class ResumeResult(Enum):
    RESUMED = "resumed"
    BUSY = "busy"
    NOT_WAITING = "not_waiting"


def _is_usage_limit_wait(goal: Goal | None) -> bool:
    return (
        goal is not None
        and goal.status is GoalStatus.WAIT
        and goal.metadata.get(GOAL_WAIT_KIND_KEY) == GOAL_WAIT_KIND_USAGE_LIMIT
    )


def _resume_at(goal: Goal) -> float | None:
    try:
        return datetime.fromisoformat(str(goal.metadata.get(GOAL_WAIT_RESUME_AT_KEY))).timestamp()
    except ValueError:
        return None


def _daemon_resume_at(goal: Goal | None) -> float | None:
    """Resume time of a goal this daemon owns, else None."""
    if goal is None or not _is_usage_limit_wait(goal) or goal.metadata.get(WAKE_OWNER_KEY) != WAKE_OWNER:
        return None
    return _resume_at(goal)


async def _resume(provider: GoalProvider, session_id: str, goal: Goal) -> bool:
    """Leave WAIT and start the unattended stream. False when the session cannot take a turn right now."""
    gateway = get_agent_gateway()
    if gateway.is_draining or gateway.is_session_active(session_id):
        return False

    await provider.exit_wait(goal.goal_id)
    resumed = await provider.get_goal(goal.goal_id)
    if resumed is None or resumed.status is not GoalStatus.ACTIVE:
        logger.warning("Goal %s did not reach ACTIVE after its usage limit reset", goal.goal_id)
        return True

    logger.info("Goal %s resumes after its usage limit reset", goal.goal_id)
    started = await trigger_goal_stream_with_failure_policy(
        session_id, resumed, provider, on_failure="needs_human_review", context="usage limit resume"
    )
    if started:
        await publish_goal_usage_limit_notification(session_id, goal.goal_id, "resumed")
    return True


async def resume_goal_after_usage_limit(session_id: str) -> ResumeResult:
    """Manual "retry now": end the usage-limit wait immediately instead of at the reset time."""
    provider = GoalRegistry.get_or_create_provider(session_id)
    goal = await provider.get_latest_goal(session_id)
    if goal is None or not _is_usage_limit_wait(goal):
        return ResumeResult.NOT_WAITING
    try:
        resumed = await _resume(provider, session_id, goal)
    except ValueError:
        return ResumeResult.NOT_WAITING
    if not resumed:
        return ResumeResult.BUSY
    get_usage_limit_wake_daemon().disarm(session_id)
    return ResumeResult.RESUMED


class UsageLimitWakeDaemon:
    """In-memory armed set plus a single wall-clock polling task."""

    def __init__(self, clock: Callable[[], float] = time.time) -> None:
        self._clock = clock
        self._armed: dict[str, float] = {}
        self._errors: dict[str, int] = {}
        self._changed = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    def arm(self, session_id: str, resume_at: float) -> None:
        self._armed[session_id] = resume_at + _WAKE_MARGIN_S
        self._changed.set()

    def disarm(self, session_id: str) -> None:
        self._armed.pop(session_id, None)
        self._errors.pop(session_id, None)

    def next_due_at(self, after: float) -> float | None:
        """Earliest armed wake time later than ``after``; earlier ones are already being handled."""
        return min((at for at in self._armed.values() if at > after), default=None)

    async def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        await self._rebuild()
        self._task = asyncio.create_task(self._run(), name="usage-limit-wake-daemon")

    async def stop(self) -> None:
        task, self._task = self._task, None
        if task is None:
            return
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    async def _rebuild(self) -> None:
        """Re-arm every goal still parked for this daemon after a restart."""
        from myrm_agent_harness.agent.goals.storage import GoalStorage
        from myrm_agent_harness.toolkits.storage.factory import get_storage_provider

        try:
            storage = GoalStorage(get_storage_provider())
            floor = self._clock() + _STARTUP_GRACE_S
            for session_id in await storage.list_latest_goal_sessions():
                goal_id = await storage.get_latest_goal_id(session_id)
                resume_at = _daemon_resume_at(await storage.get_goal(goal_id) if goal_id else None)
                if resume_at is not None:
                    self._armed[session_id] = max(resume_at + _WAKE_MARGIN_S, floor)
        except Exception:
            logger.exception("Could not rebuild usage-limit wake set from storage")
        if self._armed:
            logger.info("Usage-limit wake daemon armed %d goal(s) from storage", len(self._armed))

    async def _run(self) -> None:
        while True:
            await self._wake_due()
            await self._sleep_until_next()

    async def _sleep_until_next(self) -> None:
        self._changed.clear()
        if not self._armed:
            await self._changed.wait()
            return
        delay = min(_POLL_MAX_S, max(_POLL_MIN_S, min(self._armed.values()) - self._clock()))
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(self._changed.wait(), delay)

    async def _wake_due(self) -> None:
        now = self._clock()
        for session_id, due_at in [(sid, at) for sid, at in self._armed.items() if at <= now]:
            try:
                retry_at = await self._wake(session_id)
                self._errors.pop(session_id, None)
            except Exception:
                retry_at = self._retry_after_error(session_id)
            # A resumed stream may already have re-armed the session for a later window.
            if self._armed.get(session_id) == due_at:
                if retry_at is None:
                    self._armed.pop(session_id, None)
                else:
                    self._armed[session_id] = retry_at

    def _retry_after_error(self, session_id: str) -> float | None:
        failures = self._errors[session_id] = self._errors.get(session_id, 0) + 1
        if failures >= _MAX_WAKE_ERRORS:
            logger.exception("Giving up waking session %s after %d failures", session_id, failures)
            self._errors.pop(session_id, None)
            return None
        logger.exception("Waking session %s failed (attempt %d)", session_id, failures)
        return self._clock() + _ERROR_RETRY_S

    async def _wake(self, session_id: str) -> float | None:
        """Resume one due session. Returns when to look again, or None when it needs no more attention."""
        provider = GoalRegistry.get_or_create_provider(session_id)
        goal = await provider.get_latest_goal(session_id)
        resume_at = _daemon_resume_at(goal)
        if goal is None or resume_at is None:
            return None  # the user resumed, paused or cancelled it meanwhile

        now = self._clock()
        if resume_at + _WAKE_MARGIN_S > now:
            return resume_at + _WAKE_MARGIN_S  # parked again for a later window
        if now - resume_at > PROVIDER_WINDOW_HOLD_MAX_S:
            paused = await pause_goal_after_missed_wake(provider, goal)
            await publish_goal_usage_limit_notification(session_id, paused.goal_id, "paused")
            return None
        try:
            resumed = await _resume(provider, session_id, goal)
        except ValueError:
            return None  # left WAIT between the read and the resume
        return None if resumed else now + _BUSY_RETRY_S


_daemon: UsageLimitWakeDaemon | None = None


def get_usage_limit_wake_daemon() -> UsageLimitWakeDaemon:
    global _daemon
    if _daemon is None:
        _daemon = UsageLimitWakeDaemon()
    return _daemon
