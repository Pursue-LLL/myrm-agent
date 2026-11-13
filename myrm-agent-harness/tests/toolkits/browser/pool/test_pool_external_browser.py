"""Unit tests for GlobalBrowserPool around browsers it did not launch (CDP, remote, extension).

Covers crash accounting, stats, health and the lifecycle tick: a browser the user owns disconnecting or going quiet is
not a crash of the pool's own.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from myrm_agent_harness.toolkits.browser.pool import GlobalBrowserPool
from myrm_agent_harness.toolkits.browser.pool.browser_launcher import BrowserInstance
from myrm_agent_harness.toolkits.browser.pool.config import BrowserConfig, LaunchMode

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_browser(contexts: int = 0) -> MagicMock:
    browser = MagicMock()
    browser.contexts = [MagicMock() for _ in range(contexts)]
    return browser


def _inst_with_unresponsive_page(pool: GlobalBrowserPool, is_managed: bool) -> BrowserInstance:
    """BrowserInstance whose only pooled page fails every liveness probe.

    patchright exposes Browser.version/contexts as cached properties, so the
    lifecycle tick probes liveness through page.evaluate; a page that raises
    makes the browser look dead.
    """
    browser = _mock_browser()
    browser.on = MagicMock()
    browser.close = AsyncMock()

    inst = BrowserInstance(browser=browser, is_managed=is_managed)
    inst.load = 1
    page = MagicMock()
    page.evaluate = AsyncMock(side_effect=RuntimeError("target closed"))
    page_pool = MagicMock()
    page_pool._busy = {page}
    page_pool._idle = []
    inst.page_pools = {"agent": page_pool}

    pool._browsers.append(inst)
    pool._current_pages_in_use = 1
    return inst


# ---------------------------------------------------------------------------
# CrashWatchdog: external browser awareness
# ---------------------------------------------------------------------------


class TestCrashWatchdogExternalBrowser:
    @pytest.mark.asyncio
    async def test_external_browser_disconnect_does_not_increment_crash_count(
        self,
    ) -> None:
        pool = GlobalBrowserPool(max_browsers=2)

        mock_browser = _mock_browser()
        mock_browser.on = MagicMock()
        mock_browser.close = AsyncMock()

        inst = BrowserInstance(browser=mock_browser, is_managed=False)
        inst.load = 2

        pool._browsers.append(inst)
        pool._current_pages_in_use = 2

        initial_crash_count = pool._crash_count_browser

        await pool._handle_browser_disconnected(inst)

        assert pool._crash_count_browser == initial_crash_count
        assert inst not in pool._browsers
        assert pool._current_pages_in_use == 0

        await pool.shutdown()

    @pytest.mark.asyncio
    async def test_managed_browser_disconnect_increments_crash_count(self) -> None:
        pool = GlobalBrowserPool(max_browsers=2)

        mock_browser = _mock_browser()
        mock_browser.on = MagicMock()
        mock_browser.close = AsyncMock()

        inst = BrowserInstance(browser=mock_browser, is_managed=True)
        inst.load = 1

        pool._browsers.append(inst)
        pool._current_pages_in_use = 1

        initial_crash_count = pool._crash_count_browser

        await pool._handle_browser_disconnected(inst)

        assert pool._crash_count_browser == initial_crash_count + 1
        assert inst not in pool._browsers

        await pool.shutdown()


# ---------------------------------------------------------------------------
# Pool stats: external_browsers and launch_mode fields
# ---------------------------------------------------------------------------


class TestPoolStatsExternalFields:
    @pytest.mark.asyncio
    async def test_stats_includes_launch_mode(self) -> None:
        import dataclasses

        config = dataclasses.replace(BrowserConfig.minimal(), launch_mode=LaunchMode.AUTO)
        pool = GlobalBrowserPool(max_browsers=2, config=config)

        stats = pool.stats
        assert stats["launch_mode"] == "auto"

        await pool.shutdown()

    @pytest.mark.asyncio
    async def test_stats_counts_external_browsers(self) -> None:
        pool = GlobalBrowserPool(max_browsers=3)

        managed = BrowserInstance(browser=_mock_browser(), is_managed=True)
        external = BrowserInstance(browser=_mock_browser(), is_managed=False)

        pool._browsers.extend([managed, external])

        stats = pool.stats
        assert stats["total_browsers"] == 2
        assert stats["external_browsers"] == 1

        pool._browsers.clear()
        await pool.shutdown()

    @pytest.mark.asyncio
    async def test_stats_browser_detail_includes_is_managed(self) -> None:
        pool = GlobalBrowserPool(max_browsers=2)

        inst = BrowserInstance(browser=_mock_browser(), is_managed=False)
        pool._browsers.append(inst)

        browsers = pool.stats["browsers"]
        assert isinstance(browsers, list)
        assert browsers[0]["is_managed"] is False

        pool._browsers.clear()
        await pool.shutdown()


# ---------------------------------------------------------------------------
# pool.health() includes launch_mode and external_browsers
# ---------------------------------------------------------------------------


class TestPoolHealthExternalFields:
    @pytest.mark.asyncio
    async def test_health_includes_pool_with_launch_mode(self) -> None:
        import dataclasses

        config = dataclasses.replace(BrowserConfig.minimal(), launch_mode=LaunchMode.AUTO)
        pool = GlobalBrowserPool(max_browsers=2, config=config)

        health = await pool.health()

        assert health["status"] == "healthy"
        assert "pool" in health
        pool_stats = health["pool"]
        assert isinstance(pool_stats, dict)
        assert pool_stats["launch_mode"] == "auto"

        await pool.shutdown()

    @pytest.mark.asyncio
    async def test_health_includes_external_browsers_count(self) -> None:
        pool = GlobalBrowserPool(max_browsers=3)

        managed_browser = _mock_browser()
        managed_browser.version = AsyncMock(return_value="v1")
        external_browser = _mock_browser()
        external_browser.version = AsyncMock(return_value="v2")
        managed = BrowserInstance(browser=managed_browser, is_managed=True)
        external = BrowserInstance(browser=external_browser, is_managed=False)

        pool._browsers.extend([managed, external])

        health = await pool.health()
        pool_stats = health["pool"]
        assert isinstance(pool_stats, dict)
        assert pool_stats["external_browsers"] == 1
        assert pool_stats["total_browsers"] == 2

        pool._browsers.clear()
        await pool.shutdown()


# ---------------------------------------------------------------------------
# lifecycle_tick: external browser awareness
# ---------------------------------------------------------------------------


class TestLifecycleTickExternalBrowser:
    @pytest.mark.asyncio
    async def test_lifecycle_tick_external_unresponsive_no_crash_count(self) -> None:
        pool = GlobalBrowserPool(max_browsers=2)

        inst = _inst_with_unresponsive_page(pool, is_managed=False)

        initial_crash_count = pool._crash_count_browser

        await pool._lifecycle_tick()

        assert pool._crash_count_browser == initial_crash_count
        assert inst not in pool._browsers

        await pool.shutdown()

    @pytest.mark.asyncio
    async def test_lifecycle_tick_managed_unresponsive_increments_crash_count(
        self,
    ) -> None:
        pool = GlobalBrowserPool(max_browsers=2)

        inst = _inst_with_unresponsive_page(pool, is_managed=True)

        initial_crash_count = pool._crash_count_browser

        await pool._lifecycle_tick()

        assert pool._crash_count_browser == initial_crash_count + 1
        assert inst not in pool._browsers

        await pool.shutdown()

    @pytest.mark.asyncio
    async def test_lifecycle_tick_healthy_page_kept(self) -> None:
        pool = GlobalBrowserPool(max_browsers=2)

        browser = _mock_browser()
        browser.on = MagicMock()
        browser.close = AsyncMock()
        inst = BrowserInstance(browser=browser, is_managed=True)
        inst.load = 1
        page = MagicMock()
        page.evaluate = AsyncMock(return_value=1)
        page_pool = MagicMock()
        page_pool._busy = {page}
        page_pool._idle = []
        inst.page_pools = {"agent": page_pool}
        pool._browsers.append(inst)
        pool._current_pages_in_use = 1

        initial_crash_count = pool._crash_count_browser

        await pool._lifecycle_tick()

        assert pool._crash_count_browser == initial_crash_count
        assert inst in pool._browsers

        await pool.shutdown()

    @pytest.mark.asyncio
    async def test_lifecycle_tick_browser_without_pages_kept(self) -> None:
        pool = GlobalBrowserPool(max_browsers=2)

        browser = _mock_browser()
        browser.on = MagicMock()
        browser.close = AsyncMock()
        inst = BrowserInstance(browser=browser, is_managed=True)
        inst.load = 1
        pool._browsers.append(inst)
        pool._current_pages_in_use = 1

        initial_crash_count = pool._crash_count_browser

        await pool._lifecycle_tick()

        assert pool._crash_count_browser == initial_crash_count
        assert inst in pool._browsers

        await pool.shutdown()

    @pytest.mark.asyncio
    async def test_lifecycle_tick_target_closed_error_treated_as_dead(
        self,
    ) -> None:
        """patchright TargetClosedError (Error subclass) must not escape the probe.

        Regression: _check_browser_alive's exception list must cover all
        patchright Error subclasses, otherwise a page that was closed while
        still pooled crashes the whole lifecycle tick via asyncio.gather.
        """
        from patchright._impl._errors import TargetClosedError

        pool = GlobalBrowserPool(max_browsers=2)

        browser = _mock_browser()
        browser.on = MagicMock()
        browser.close = AsyncMock()
        inst = BrowserInstance(browser=browser, is_managed=True)
        inst.load = 1
        page = MagicMock()
        page.evaluate = AsyncMock(side_effect=TargetClosedError("Page closed"))
        page_pool = MagicMock()
        page_pool._busy = {page}
        page_pool._idle = []
        inst.page_pools = {"agent": page_pool}
        pool._browsers.append(inst)
        pool._current_pages_in_use = 1

        initial_crash_count = pool._crash_count_browser

        await pool._lifecycle_tick()

        assert pool._crash_count_browser == initial_crash_count + 1
        assert inst not in pool._browsers

        await pool.shutdown()
