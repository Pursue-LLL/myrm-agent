"""Real-Chromium proof that the pool serves pages again after its Playwright driver was killed.

The driver is the Node process every launched browser hangs off. Killing it ends the browser too, yet the browser
object still reports itself connected and fires no 'disconnected' event, so only the pool's health tick can notice.
Run with: `pytest -m integration tests/toolkits/browser/pool/test_driver_death_recovery.py`.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator

import psutil
import pytest

from myrm_agent_harness.toolkits.browser.pool import ContextType, GlobalBrowserPool
from tests.toolkits.browser._browser_available import chromium_available

pytestmark = [
    pytest.mark.integration,
    pytest.mark.slow,
    pytest.mark.asyncio,
    pytest.mark.skipif(not chromium_available(), reason="Chromium not available"),
]

_CONTEXT_KEY = "driver-death"
_RECOVERY_TIMEOUT_S = 60.0


@pytest.fixture
async def pool() -> AsyncIterator[GlobalBrowserPool]:
    browser_pool = GlobalBrowserPool(max_browsers=1)
    yield browser_pool
    with contextlib.suppress(Exception):
        await asyncio.wait_for(browser_pool.shutdown(), timeout=20.0)


def _driver_processes() -> dict[int, psutil.Process]:
    """The Playwright drivers this process started (the bundled `driver/node` executable)."""
    drivers: dict[int, psutil.Process] = {}
    for child in psutil.Process().children(recursive=True):
        with contextlib.suppress(psutil.Error):  # a Chromium helper may exit while the list is walked
            argv = child.cmdline()
            if argv and "/driver/" in argv[0].replace("\\", "/"):
                drivers[child.pid] = child
    return drivers


async def _page_answers(pool: GlobalBrowserPool) -> bool:
    page, key = await pool.acquire_page(ContextType.AGENT, context_key=_CONTEXT_KEY)
    try:
        return await page.evaluate("1 + 1") == 2
    finally:
        await pool.release_page(page, key)


async def _warm_up_and_kill_the_driver(pool: GlobalBrowserPool) -> tuple[set[int], set[int]]:
    """Serve one page, then SIGKILL the driver the pool started. Returns (drivers before the pool, drivers killed)."""
    before = set(_driver_processes())
    assert await _page_answers(pool)
    started = {pid: proc for pid, proc in _driver_processes().items() if pid not in before}
    assert len(started) == 1, f"expected exactly one new driver process, found {sorted(started)}"
    for driver in started.values():
        driver.kill()
    return before, set(started)


async def _assert_pool_serves_again(pool: GlobalBrowserPool, before: set[int], killed: set[int]) -> None:
    await pool._lifecycle_tick()  # the health check drops the browser the dead driver left behind
    async with asyncio.timeout(_RECOVERY_TIMEOUT_S):
        assert await _page_answers(pool)
    replacements = set(_driver_processes()) - before - killed  # the killed driver may linger as a zombie
    assert len(replacements) == 1, f"expected exactly one new driver process, found {sorted(replacements)}"


async def test_the_pool_serves_pages_again_after_the_driver_is_killed(pool: GlobalBrowserPool) -> None:
    before, killed = await _warm_up_and_kill_the_driver(pool)

    await _assert_pool_serves_again(pool, before, killed)


async def test_callers_arriving_while_the_driver_is_dead_do_not_keep_the_pool_down(pool: GlobalBrowserPool) -> None:
    """Every failed acquisition also throws away the dead browser's idle pages; a browser without pages is still dead."""
    before, killed = await _warm_up_and_kill_the_driver(pool)
    for _ in range(3):
        with contextlib.suppress(Exception):
            await _page_answers(pool)

    await _assert_pool_serves_again(pool, before, killed)
