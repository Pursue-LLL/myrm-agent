"""Read-only monitoring of the global pool: statistics, health report and page ownership.

[INPUT]
- .browser_launcher::BrowserInstance (POS: browser instance metadata)
- .circuit_breaker::CircuitBreaker (POS: circuit breaker whose counters join the statistics)
- .config::BrowserPoolConfig (POS: limits the statistics are reported against)
- .proxy::ProxyPool (POS: proxy pool whose active sessions join the statistics)

[OUTPUT]
- PoolDiagnosticsMixin: `is_managed_for_page`, `stats` and `health` for GlobalBrowserPool

[POS]
What monitoring and the takeover UI ask the pool. Nothing here changes the pool: `stats` is a
snapshot of its counters, `health` probes every browser concurrently on top of it, and `is_managed_for_page` tells
whether a page belongs to a browser the pool launched (the VNC path) or to an attached one.
"""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING

from .browser_launcher import BrowserInstance

if TYPE_CHECKING:
    from patchright.async_api import Page

    from .circuit_breaker import CircuitBreaker
    from .config import BrowserPoolConfig
    from .proxy import ProxyPool


class PoolDiagnosticsMixin:
    """Statistics, health and page ownership queries for GlobalBrowserPool.

    Requires host class to have:
    - _browsers: list[BrowserInstance]
    - _config: BrowserPoolConfig
    - _current_pages_in_use / _total_acquires / _total_releases: pool counters
    - _crash_count_browser / _crash_count_page: crash counters
    - _lifecycle_task: asyncio.Task[None] | None
    - _circuit_breaker: CircuitBreaker | None
    - _proxy_pool: ProxyPool | None
    """

    _browsers: list[BrowserInstance]
    _config: BrowserPoolConfig
    _current_pages_in_use: int
    _total_acquires: int
    _total_releases: int
    _crash_count_browser: int
    _crash_count_page: int
    _lifecycle_task: asyncio.Task[None] | None
    _circuit_breaker: CircuitBreaker | None
    _proxy_pool: ProxyPool | None

    if TYPE_CHECKING:

        @staticmethod
        async def _check_browser_alive(inst: BrowserInstance) -> bool: ...

    def is_managed_for_page(self, page: Page) -> bool:
        """Return True when the page belongs to a sandbox-launched browser (VNC path).

        CDP-attached browsers (connect/auto/extension) return False.
        """
        try:
            browser = page.context.browser
        except Exception:
            return True

        for inst in self._browsers:
            if inst.browser is browser:
                return inst.is_managed
        return True

    @property
    def stats(self) -> dict[str, object]:
        """Get global statistics (for monitoring)."""
        current_in_use = self._current_pages_in_use
        available = self._config.max_concurrent_pages - current_in_use
        now = time.monotonic()
        browsers_snapshot = self._browsers
        return {
            "total_browsers": len(browsers_snapshot),
            "external_browsers": sum(1 for b in browsers_snapshot if not b.is_managed),
            "total_contexts": sum(len(b.contexts) for b in browsers_snapshot),
            "total_load": sum(b.load for b in browsers_snapshot),
            "total_acquires": self._total_acquires,
            "total_releases": self._total_releases,
            "current_pages_in_use": current_in_use,
            "available_slots": available,
            "max_concurrent_pages": self._config.max_concurrent_pages,
            "launch_mode": self._config.launch_mode.value,
            "utilization_percent": round(current_in_use / self._config.max_concurrent_pages * 100, 2),
            "lifecycle_active": self._lifecycle_task is not None and not self._lifecycle_task.done(),
            "idle_timeout_seconds": self._config.idle_timeout_seconds,
            "crash_count_browser": self._crash_count_browser,
            "crash_count_page": self._crash_count_page,
            "browsers": [
                {
                    "load": b.load,
                    "contexts": len(b.contexts),
                    "idle_seconds": round(now - b.last_active_at, 1),
                    "is_managed": b.is_managed,
                    "pools": {k: v.stats for k, v in b.page_pools.items()},
                }
                for b in browsers_snapshot
            ],
            "circuit_breaker": self._circuit_breaker.stats if self._circuit_breaker else {},
            "proxy_pool_active_sessions": self._proxy_pool.active_session_count if self._proxy_pool else 0,
        }

    async def health(self) -> dict[str, object]:
        """Get runtime health status for monitoring and diagnostics.

        Returns:
            Health status dictionary with:
            - status: "healthy" | "degraded" | "unhealthy"
            - pool: Current pool statistics
            - browsers_alive: Number of browsers with successful version() call
            - browsers_total: Total number of browser instances
            - memory: Current memory usage (if psutil available)
            - issues: List of detected issues
        """
        issues: list[str] = []

        pool_stats = self.stats
        utilization = round(self._current_pages_in_use / self._config.max_concurrent_pages * 100, 2)

        if utilization > 90:
            issues.append(f"High utilization: {utilization:.0f}%")

        browsers_snapshot = list(self._browsers)
        browsers_total = len(browsers_snapshot)

        async def _probe(index: int, inst: BrowserInstance) -> tuple[int, bool]:
            return index, await self._check_browser_alive(inst)

        results = await asyncio.gather(
            *[_probe(i, b) for i, b in enumerate(browsers_snapshot)],
            return_exceptions=True,
        )

        browsers_alive = 0
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                issues.append(f"Browser #{i} check failed: {type(result).__name__}")
            elif isinstance(result, tuple):
                index, alive = result
                if alive:
                    browsers_alive += 1
                else:
                    issues.append(f"Browser #{index} unresponsive")

        memory_info: dict[str, object] = {}
        try:
            import psutil

            mem = psutil.virtual_memory()
            memory_info = {
                "available_gb": round(mem.available / (1024**3), 2),
                "used_percent": mem.percent,
            }
            if mem.available < 1024**3:
                issues.append(f"Low memory: {memory_info['available_gb']} GB available")
        except (ImportError, TypeError):
            pass

        if browsers_alive == 0 and browsers_total > 0:
            status = "unhealthy"
        elif issues:
            status = "degraded"
        else:
            status = "healthy"

        return {
            "status": status,
            "pool": pool_stats,
            "browsers_alive": browsers_alive,
            "browsers_total": browsers_total,
            "crash_count_browser": self._crash_count_browser,
            "crash_count_page": self._crash_count_page,
            "memory": memory_info,
            "issues": issues,
        }
