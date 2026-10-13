"""The scheduler loop, the wake-up heartbeat and the guard together on a virtual clock.

The unit tests poke the guard's private ticks. Here the loop sleeps (virtually) through the 15-minute
initial delay and the six-hour interval, so a guard that mistook plain idle time for a system resume
would starve T2 for as long as the process runs.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from myrm_agent_harness.toolkits.memory.health import MaintenanceReport

from app.lifecycle.cognitive_clock import coordinator as coordinator_module
from app.lifecycle.cognitive_clock import wakeup_guard
from app.lifecycle.cognitive_clock.coordinator import CognitiveClockCoordinator
from app.services.memory.ledger.guardian_policy import MemoryGuardianPolicy

_INITIAL_DELAY_SECONDS = 15 * 60.0
_BALANCED_INTERVAL_SECONDS = 6 * 3600.0
_SUPPRESSION_RETRY_SECONDS = 15 * 60.0


class _VirtualClockLoop(asyncio.SelectorEventLoop):
    """Event loop whose clock jumps to the next timer instead of waiting for it."""

    def __init__(self) -> None:
        super().__init__()
        self._now = 0.0

    def time(self) -> float:
        return self._now

    def _run_once(self) -> None:
        if not self._ready and self._scheduled:
            self._now = max(self._now, self._scheduled[0]._when)
        super()._run_once()


class _HostClock:
    """Wall and monotonic clock of one host, driven by the virtual loop.

    ``suspend_host`` moves only the wall clock, like a sleeping machine whose monotonic clock stands still.
    """

    def __init__(self, loop: _VirtualClockLoop) -> None:
        self._loop = loop
        self._suspended_seconds = 0.0

    def monotonic(self) -> float:
        return self._loop.time()

    def time(self) -> float:
        return 1.7e9 + self._loop.time() + self._suspended_seconds

    def suspend_host(self, seconds: float) -> None:
        self._suspended_seconds += seconds


def test_t2_keeps_its_cadence_across_idle_time_and_host_suspends(monkeypatch: pytest.MonkeyPatch) -> None:
    loop = _VirtualClockLoop()
    host = _HostClock(loop)
    monkeypatch.setattr(wakeup_guard, "time", host)

    t2_runs: list[float] = []

    async def run_t2(*, force: bool, policy: MemoryGuardianPolicy) -> tuple[MaintenanceReport, None]:
        t2_runs.append(loop.time())
        return MaintenanceReport(skipped=False), None

    t3 = AsyncMock()
    monkeypatch.setattr(coordinator_module, "load_memory_guardian_policy", AsyncMock(return_value=MemoryGuardianPolicy()))
    monkeypatch.setattr(coordinator_module, "execute_t2_idle_maintenance", run_t2)
    monkeypatch.setattr(coordinator_module, "execute_t3_epoch_discovery", t3)
    monkeypatch.setattr(coordinator_module, "get_maintenance_scheduler", lambda: None)
    monkeypatch.setattr("app.services.agent.gateway.get_agent_gateway", lambda: SimpleNamespace(active_count=0))
    monkeypatch.setattr("app.services.budget.enforcer.should_block_execution", AsyncMock(return_value=False))

    first_pass = _INITIAL_DELAY_SECONDS
    second_pass = first_pass + _BALANCED_INTERVAL_SECONDS
    third_pass = second_pass + _BALANCED_INTERVAL_SECONDS
    retried_third_pass = third_pass + _SUPPRESSION_RETRY_SECONDS

    async def scenario() -> None:
        scheduler = CognitiveClockCoordinator()
        scheduler.start()
        try:
            await asyncio.sleep(first_pass + 1)
            # Nothing read the guard during the whole initial delay; that idle time is no resume.
            assert t2_runs == [first_pass]

            # The host suspends an hour into the interval: by the next pass the resume is long over.
            await asyncio.sleep(3600)
            host.suspend_host(3600.0)
            await asyncio.sleep(second_pass + 1 - loop.time())
            assert t2_runs == [first_pass, second_pass]

            # The host suspends a minute before the next pass: the pass waits out the grace period and retries.
            await asyncio.sleep(third_pass - 60 - loop.time())
            host.suspend_host(3600.0)
            await asyncio.sleep(61)
            assert t2_runs == [first_pass, second_pass]
            await asyncio.sleep(_SUPPRESSION_RETRY_SECONDS)
            assert t2_runs == [first_pass, second_pass, retried_third_pass]
        finally:
            await scheduler.stop()

    try:
        loop.run_until_complete(scenario())
    finally:
        loop.close()

    t3.assert_awaited_once()
