"""A navigation that lands while a readiness probe runs must not escape the wait.

The probe evaluates inside the document it is waiting for. When that document navigates away (a script
redirect, a late ``location`` assignment), patchright reports it as a bare ``Error`` - neither a timeout
nor a ``RuntimeError`` - and it must not surface from ``navigate()``. The wait re-arms on the new
document with the budget that is left, and every strategy shares that behaviour.
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from patchright.async_api import Error as BrowserDriverError

from myrm_agent_harness.toolkits.browser.wait import WaitStrategy, wait_for_page_ready
from myrm_agent_harness.toolkits.browser.wait._impl import is_navigation_interrupt
from myrm_agent_harness.toolkits.web_fetch.router import DomainMetricsManager

_NAVIGATED_AWAY = "Page.evaluate: Execution context was destroyed, most likely because of a navigation."
_TARGET_CLOSED = "Page.evaluate: Target page, context or browser has been closed"
_QUIET = {"reason": "quiet", "elapsed_ms": 5, "mutation_count": 0, "reset_count": 0, "shadow_count": 0}


class _Probe:
    """A page whose first evaluation (and first load-state wait) is interrupted by a navigation."""

    def __init__(self, *, interrupted_calls: int = 1, network_hangs: bool = False) -> None:
        self.interrupted_calls = interrupted_calls
        self.network_hangs = network_hangs
        self.evaluations = 0
        self.network_started = 0
        self.network_cancelled = 0
        self.page = MagicMock()
        self.page.evaluate = self._evaluate
        self.page.wait_for_load_state = self._wait_for_load_state

    async def _evaluate(self, _expression: str) -> dict[str, object]:
        self.evaluations += 1
        if self.evaluations <= self.interrupted_calls:
            raise BrowserDriverError(_NAVIGATED_AWAY)
        return dict(_QUIET)

    async def _wait_for_load_state(self, _state: str, timeout: float) -> None:
        self.network_started += 1
        if not self.network_hangs:
            if self.network_started <= self.interrupted_calls:
                raise BrowserDriverError(_NAVIGATED_AWAY)
            return
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            self.network_cancelled += 1
            raise


def test_only_a_navigation_destroying_the_context_counts_as_an_interruption() -> None:
    assert is_navigation_interrupt(BrowserDriverError(_NAVIGATED_AWAY))
    assert not is_navigation_interrupt(BrowserDriverError(_TARGET_CLOSED))
    assert not is_navigation_interrupt(RuntimeError(_NAVIGATED_AWAY))


@pytest.mark.parametrize(
    "strategy",
    [
        WaitStrategy.HYBRID,
        WaitStrategy.SMART,
        WaitStrategy.DOM_STABLE,
        WaitStrategy.SPA_STABLE,
        WaitStrategy.NETWORKIDLE,
    ],
)
async def test_every_strategy_rearms_after_an_interrupted_probe(strategy: WaitStrategy) -> None:
    probe = _Probe()

    metrics = await wait_for_page_ready(probe.page, strategy=strategy, max_ms=2000, quiet_ms=50, grace_period_ms=50)

    assert metrics.strategy == strategy
    assert metrics.reason != "capped"


async def test_a_hybrid_probe_interrupted_midway_leaves_no_task_behind() -> None:
    probe = _Probe(network_hangs=True)

    metrics = await wait_for_page_ready(
        probe.page, strategy=WaitStrategy.HYBRID, max_ms=2000, quiet_ms=50, grace_period_ms=50
    )

    assert probe.evaluations == 2
    assert metrics.reason == "first_completed"
    assert probe.network_started == probe.network_cancelled == 2


async def test_a_page_that_keeps_navigating_is_given_up_on_at_the_budget() -> None:
    probe = _Probe(interrupted_calls=1_000, network_hangs=True)
    started = time.perf_counter()

    metrics = await wait_for_page_ready(probe.page, strategy=WaitStrategy.HYBRID, max_ms=400, quiet_ms=50)

    assert metrics.reason == "capped"
    assert 0.3 <= time.perf_counter() - started < 1.5
    assert metrics.elapsed_ms >= 300
    assert probe.network_started == probe.network_cancelled


async def test_any_other_driver_error_still_propagates() -> None:
    page = MagicMock()
    page.evaluate = AsyncMock(side_effect=BrowserDriverError(_TARGET_CLOSED))
    page.wait_for_load_state = AsyncMock(return_value=None)

    with pytest.raises(BrowserDriverError, match="has been closed"):
        await wait_for_page_ready(page, strategy=WaitStrategy.HYBRID, max_ms=500, quiet_ms=50)


async def test_a_domain_without_history_takes_the_fast_path(tmp_path: Path) -> None:
    manager = DomainMetricsManager(storage_path=tmp_path / "domain_metrics.json")
    probe = _Probe(interrupted_calls=0)
    probe.page.wait_for_load_state = AsyncMock(return_value=None)
    # One earlier visit is a single sample: not enough to say networkidle fails on this domain.
    manager.get_or_create("example.com").record_networkidle_result(success=True)

    await wait_for_page_ready(
        probe.page,
        strategy=WaitStrategy.SMART,
        max_ms=2000,
        domain="example.com",
        domain_metrics_manager=manager,
    )

    probe.page.wait_for_load_state.assert_not_awaited()


async def test_a_domain_where_networkidle_keeps_failing_goes_straight_to_the_hybrid_probe(tmp_path: Path) -> None:
    manager = DomainMetricsManager(storage_path=tmp_path / "domain_metrics.json")
    probe = _Probe(interrupted_calls=0)
    probe.page.wait_for_load_state = AsyncMock(return_value=None)
    unreliable = manager.get_or_create("example.com")
    for _ in range(20):
        unreliable.record_networkidle_result(success=False)

    await wait_for_page_ready(
        probe.page,
        strategy=WaitStrategy.SMART,
        max_ms=2000,
        quiet_ms=50,
        grace_period_ms=50,
        domain="example.com",
        domain_metrics_manager=manager,
    )

    probe.page.wait_for_load_state.assert_awaited()
