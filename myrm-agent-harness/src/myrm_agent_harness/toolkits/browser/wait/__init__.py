"""Page wait strategies — hybrid detection for optimal page ready detection.


[INPUT]
- _types (POS: type definitions and statistics)
- _impl (POS: strategy implementations)
- _action_settle (POS: the wait an interaction ends with)
- patchright.async_api::Page (POS: Patchright page instance)
- time::perf_counter (POS: high-precision timer)
- logging::getLogger (POS: Python logging)

[OUTPUT]
- WaitStrategy: wait strategy enum (4 types: smart/hybrid/dom_stable/networkidle)
- WaitMetrics: wait metrics (full observability)
- WaitStrategyStats: runtime statistics class (thread-safe)
- wait_for_page_ready: page readiness detection entry point (default SMART strategy, auto-records stats)
- settle_after_action: the wait an interaction ends with (the requests the action started, not page quiet)
- get_wait_strategy_stats: retrieve global statistics
- reset_wait_strategy_stats: reset statistics (for testing)

[POS]
Page wait strategy module. Provides 4 wait strategies:
1. SMART adaptive: tries networkidle first (fast), falls back to hybrid (accurate) on timeout
2. HYBRID: DOM stability + network idle dual detection (first-to-complete + grace period)
3. DOM_STABLE: MutationObserver monitors DOM changes (including Shadow DOM)
4. NETWORKIDLE: Playwright native network idle detection

Features:
- Smart filtering: excludes animation attributes (style/class/aria-*) to reduce false positives
- Shadow DOM support: recursively observes all shadowRoots
- JavaScript caching: @lru_cache avoids redundant generation
- Full metrics: elapsed_ms, dom_stable_ms, network_idle_ms, shadow_dom_count
- Runtime statistics: global stats class records strategy usage and hit rates (thread-safe)
- Parameter validation: max_ms/quiet_ms/grace_period_ms legality checks
- Resource cleanup: complete cleanup after Task cancellation to avoid ResourceWarning

Module structure:
- _types.py: type definitions (WaitStrategy/WaitMetrics/WaitStrategyStats) and runtime stats
- _impl.py: 4 strategy implementations (networkidle/dom_stable/smart/hybrid)
- _dom_stable_js.py: DOM stability detection JavaScript generator
- _action_settle.py: the wait after an interaction (not a readiness strategy: it waits for what the action started)
- __init__.py: public interface (this file)
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import replace
from typing import TYPE_CHECKING

from ._action_settle import settle_after_action
from ._impl import (
    _elapsed_ms_since,
    is_navigation_interrupt,
    wait_dom_stable_only,
    wait_hybrid,
    wait_networkidle_only,
    wait_smart,
    wait_spa_stable,
)
from ._types import (
    WaitMetrics,
    WaitStrategy,
    WaitStrategyStats,
    _global_stats,
    get_wait_strategy_stats,
    reset_wait_strategy_stats,
)

if TYPE_CHECKING:
    from patchright.async_api import Page

    from myrm_agent_harness.toolkits.web_fetch.router.domain_metrics import (
        DomainMetricsManager,
    )

logger = logging.getLogger(__name__)

# A wait re-armed after a navigation needs room for at least one meaningful probe; below this the
# page is reported as capped instead. The pause keeps a document that fails instantly from being
# probed in a hot loop while the navigation is still committing.
_REARM_MIN_BUDGET_MS = 100
_REARM_PAUSE_S = 0.05


async def _run_strategy(
    page: Page,
    strategy: WaitStrategy,
    max_ms: int,
    quiet_ms: int,
    grace_period_ms: int,
    domain: str | None,
    domain_metrics_manager: DomainMetricsManager | None,
) -> WaitMetrics:
    """Run one attempt of ``strategy`` against the current document."""
    start_time = time.perf_counter()
    if strategy == WaitStrategy.NETWORKIDLE:
        return await wait_networkidle_only(page, max_ms, start_time)
    if strategy == WaitStrategy.DOM_STABLE:
        return await wait_dom_stable_only(page, max_ms, quiet_ms, start_time)
    if strategy == WaitStrategy.SPA_STABLE:
        return await wait_spa_stable(page, max_ms, start_time)
    if strategy == WaitStrategy.SMART:
        return await wait_smart(
            page,
            max_ms,
            quiet_ms,
            grace_period_ms,
            start_time,
            domain,
            domain_metrics_manager,
        )
    return await wait_hybrid(page, max_ms, quiet_ms, grace_period_ms, start_time)


def _record_to_domain_metrics(metrics: WaitMetrics, domain: str, domain_metrics_manager: DomainMetricsManager) -> None:
    """Record wait metrics into the domain metrics store."""

    try:
        domain_metrics = domain_metrics_manager.get_or_create(domain)

        if metrics.strategy == WaitStrategy.NETWORKIDLE or metrics.reason == "network_only":
            domain_metrics.record_wait_strategy("networkidle", metrics.elapsed_ms)
            domain_metrics.record_networkidle_result(success=metrics.reason == "network_only")

        elif metrics.strategy in (WaitStrategy.HYBRID, WaitStrategy.SMART):
            if metrics.network_idle_ms is not None:
                domain_metrics.record_networkidle_result(success=True)
            elif metrics.reason != "network_only":
                domain_metrics.record_networkidle_result(success=False)

            if metrics.dom_stable_ms is not None:
                domain_metrics.record_wait_strategy("dom_stable", metrics.dom_stable_ms)

        elif metrics.strategy in (WaitStrategy.DOM_STABLE, WaitStrategy.SPA_STABLE):
            domain_metrics.record_wait_strategy("dom_stable", metrics.elapsed_ms)

    except Exception as e:
        logger.warning(f"Failed to record wait metrics for {domain}: {e}")


async def wait_for_page_ready(
    page: Page,
    *,
    strategy: WaitStrategy = WaitStrategy.SMART,
    max_ms: int = 5000,
    quiet_ms: int = 500,
    grace_period_ms: int = 200,
    domain: str | None = None,
    domain_metrics_manager: DomainMetricsManager | None = None,
) -> WaitMetrics:
    """Wait until the page is considered ready.

    Args:
        page: Patchright page instance
        strategy: Wait strategy to use (default SMART: adaptive fast + accurate)
        max_ms: Hard timeout for the whole wait (must be > 0)
        quiet_ms: Quiet window; no DOM changes within this window counts as stable
        grace_period_ms: Extra time granted to the second task in hybrid strategy
        domain: Domain used for per-domain learning (SMART strategy)
        domain_metrics_manager: Manager to read/write historical metrics

    A navigation that destroys the probe's document (script redirect, late ``location`` assignment)
    re-arms the wait on the new document with the remaining budget; a page that keeps navigating is
    reported as capped at ``max_ms``.

    Returns:
        WaitMetrics: complete wait metrics

    Raises:
        ValueError: Parameter validation failed (negative/zero values)

    Examples:
        # Adaptive detection (balanced performance + accuracy)
        metrics = await wait_for_page_ready(page, strategy=WaitStrategy.SMART)
        logger.info(f"Page ready: {metrics.reason}, elapsed={metrics.elapsed_ms}ms")

        # Domain-level optimization based on historical data
        metrics = await wait_for_page_ready(
            page,
            strategy=WaitStrategy.SMART,
            domain="example.com",
            domain_metrics_manager=manager
        )

        # Hybrid detection (accuracy first)
        metrics = await wait_for_page_ready(page, strategy=WaitStrategy.HYBRID)

        # DOM-only detection (fast mode)
        metrics = await wait_for_page_ready(
            page,
            strategy=WaitStrategy.DOM_STABLE,
            max_ms=3000
        )
    """
    if max_ms <= 0:
        raise ValueError(f"max_ms must be positive, got {max_ms}")
    if quiet_ms < 0:
        raise ValueError(f"quiet_ms must be non-negative, got {quiet_ms}")
    if grace_period_ms < 0:
        raise ValueError(f"grace_period_ms must be non-negative, got {grace_period_ms}")

    if quiet_ms > max_ms:
        logger.warning(f"quiet_ms ({quiet_ms}ms) exceeds max_ms ({max_ms}ms), adjusting to {max_ms}ms")
        quiet_ms = max_ms

    started = time.perf_counter()
    budget_ms = max_ms
    interruptions = 0
    while True:
        try:
            metrics = await _run_strategy(
                page,
                strategy,
                budget_ms,
                min(quiet_ms, budget_ms),
                grace_period_ms,
                domain,
                domain_metrics_manager,
            )
            break
        except Exception as exc:
            if not is_navigation_interrupt(exc):
                raise
        # A navigation destroyed the document the probe was evaluating in. The page it leads to is the one
        # to judge, with the budget that is left; a page that never stops navigating is given up on at max_ms.
        interruptions += 1
        await asyncio.sleep(_REARM_PAUSE_S)
        budget_ms = max_ms - _elapsed_ms_since(started)
        if budget_ms < _REARM_MIN_BUDGET_MS:
            metrics = WaitMetrics(strategy=strategy, reason="capped", elapsed_ms=0)
            break
        logger.debug(f"Wait: navigation interrupted the probe, re-arming with {budget_ms}ms left")

    if interruptions:
        metrics = replace(metrics, elapsed_ms=_elapsed_ms_since(started))

    _global_stats.record_call(metrics.strategy, metrics.reason, metrics.elapsed_ms)

    if domain and domain_metrics_manager:
        _record_to_domain_metrics(metrics, domain, domain_metrics_manager)

    return metrics


__all__ = [
    "WaitMetrics",
    "WaitStrategy",
    "WaitStrategyStats",
    "get_wait_strategy_stats",
    "reset_wait_strategy_stats",
    "settle_after_action",
    "wait_for_page_ready",
]
