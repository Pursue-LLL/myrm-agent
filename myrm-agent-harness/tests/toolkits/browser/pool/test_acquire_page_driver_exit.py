"""An acquisition that finds the Playwright driver gone heals the pool and succeeds on a new browser.

The driver is the Node process every launched browser hangs off. When it exits its browsers are dead, but nothing
says so: no 'disconnected' event fires, every protocol call fails with "Connection closed while reading from the
driver", and the pool keeps handing the dead browser out until a lifecycle tick evicts it. The acquisition that hit
the failure is the first to know, so it asks for that eviction itself and retries once, instead of failing and leaving
the same trap for the next caller. Only the browsers are doubles: pool, lock, semaphore, page pools and the
lifecycle tick are the real ones.
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

import pytest

from myrm_agent_harness.toolkits.browser.exceptions import BrowserLaunchError
from myrm_agent_harness.toolkits.browser.pool import ContextType, GlobalBrowserPool
from myrm_agent_harness.toolkits.browser.pool.browser_launcher import BrowserInstance
from myrm_agent_harness.toolkits.browser.pool.config import BrowserEngine, BrowserPoolConfig, LaunchMode
from myrm_agent_harness.toolkits.browser.pool.page_pool import PagePool
from tests.toolkits.browser._fake_pages import FakeCdp, FakePage

if TYPE_CHECKING:
    from patchright.async_api import Page

_LIMIT = 8
_KEY = "ctx"
_BOUND_S = 2.0
_PAGE_GONE = "BrowserContext.new_page: Connection closed while reading from the driver"
_SECOND_PAGE_GONE = f"{_PAGE_GONE} (second browser)"
_PROBE_GONE = "Browser.new_browser_cdp_session: Connection closed while reading from the driver"
_LAUNCH_GONE = "BrowserType.launch: Connection closed while reading from the driver"
_DRIVER_GONE_PATTERN = "Connection closed while reading from the driver"


def _live_probe() -> AsyncMock:
    cdp = MagicMock(send=AsyncMock(return_value={}), detach=AsyncMock())
    return AsyncMock(return_value=cdp)


def _instance(*, new_page: AsyncMock, probe: AsyncMock) -> BrowserInstance:
    context = MagicMock()
    context.new_page = new_page
    browser = MagicMock()
    browser.new_browser_cdp_session = probe
    browser.close = AsyncMock()
    return BrowserInstance(
        browser=browser,
        contexts={_KEY: context},
        page_pools={_KEY: PagePool(context, max_size=_LIMIT)},
    )


def _live_instance() -> BrowserInstance:
    return _instance(new_page=AsyncMock(side_effect=lambda: FakePage(cdp=FakeCdp())), probe=_live_probe())


def _dead_instance(page_error: str = _PAGE_GONE) -> BrowserInstance:
    """A browser whose driver exited: it still sits in the pool, and everything asked of it fails."""
    return _instance(
        new_page=AsyncMock(side_effect=Exception(page_error)),
        probe=AsyncMock(side_effect=Exception(_PROBE_GONE)),
    )


@dataclass
class Rig:
    pool: GlobalBrowserPool
    make_instance: Callable[[], BrowserInstance] = _live_instance  # what launching a browser produces
    launch_failures: list[Exception] = field(default_factory=list)  # raised by the next launches, in order
    launched: list[BrowserInstance] = field(default_factory=list)

    async def least_loaded(self, _engine: BrowserEngine, _mode: LaunchMode | None) -> BrowserInstance:
        """The pool's scheduling contract: use the browser that is there, launch one when the pool is empty."""
        if not self.pool._browsers:
            if self.launch_failures:
                raise self.launch_failures.pop(0)
            fresh = self.make_instance()
            self.launched.append(fresh)
            self.pool._browsers.append(fresh)
        return self.pool._browsers[0]

    async def take(self) -> tuple[Page, str]:
        return await self.pool.acquire_page(ContextType.AGENT, context_key=_KEY)

    def assert_conserved(self) -> None:
        assert self.pool._global_semaphore._value == _LIMIT, "permit leaked or over-released"
        assert self.pool._current_pages_in_use == 0


@pytest.fixture
def rig(monkeypatch: pytest.MonkeyPatch) -> Rig:
    pool = GlobalBrowserPool(max_browsers=1, config=BrowserPoolConfig(max_concurrent_pages=_LIMIT))
    rig = Rig(pool)
    monkeypatch.setattr(pool, "_get_least_loaded_browser", rig.least_loaded)
    monkeypatch.setattr(pool, "_ensure_lifecycle_loop", MagicMock())  # the periodic loop must not be what heals
    monkeypatch.setattr(pool._memory_guard, "check_memory", AsyncMock())
    return rig


async def test_an_acquisition_on_a_dead_driver_succeeds_on_a_new_browser(rig: Rig) -> None:
    dead = _dead_instance()
    rig.pool._browsers.append(dead)

    page, key = await rig.take()

    assert key == _KEY
    assert dead not in rig.pool._browsers, "the dead browser must leave the pool, or the next caller is handed it"
    assert len(rig.launched) == 1
    assert rig.pool._browsers == rig.launched
    assert rig.pool._crash_count_browser == 1
    assert rig.pool._global_semaphore._value == _LIMIT - 1

    await rig.pool.release_page(page, key)
    rig.assert_conserved()


async def test_a_failure_that_is_not_a_driver_exit_is_not_retried(rig: Rig, monkeypatch: pytest.MonkeyPatch) -> None:
    broken = _instance(new_page=AsyncMock(side_effect=RuntimeError("renderer limit reached")), probe=_live_probe())
    rig.pool._browsers.append(broken)
    tick = AsyncMock()
    monkeypatch.setattr(rig.pool, "_lifecycle_tick", tick)

    with pytest.raises(RuntimeError, match="renderer limit reached"):
        await rig.take()

    assert broken in rig.pool._browsers
    assert not rig.launched
    tick.assert_not_awaited()
    rig.assert_conserved()


async def test_the_acquisition_is_retried_once_and_the_second_failure_is_the_one_reported(
    rig: Rig, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig.pool._browsers.append(_dead_instance())
    rig.make_instance = lambda: _dead_instance(_SECOND_PAGE_GONE)  # the browser launched after the eviction is as dead
    tick = AsyncMock(wraps=rig.pool._lifecycle_tick)
    monkeypatch.setattr(rig.pool, "_lifecycle_tick", tick)

    with pytest.raises(Exception, match=re.escape(_SECOND_PAGE_GONE)):
        await rig.take()

    assert tick.await_count == 1, "one on-demand tick per acquisition, never a loop"
    assert len(rig.launched) == 1
    rig.assert_conserved()


async def test_a_failing_tick_is_only_logged_and_the_retry_still_reports_what_is_wrong(
    rig: Rig, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    rig.pool._browsers.append(_dead_instance())
    monkeypatch.setattr(rig.pool, "_lifecycle_tick", AsyncMock(side_effect=RuntimeError("tick exploded")))

    with caplog.at_level(logging.WARNING), pytest.raises(Exception, match=_DRIVER_GONE_PATTERN):
        await rig.take()

    assert "Lifecycle tick after a driver exit failed" in caplog.text
    rig.assert_conserved()


async def test_a_launcher_error_wrapping_the_driver_exit_is_retried(rig: Rig) -> None:
    failure = BrowserLaunchError("Browser launch failed after 3 attempts")
    failure.__cause__ = Exception(_LAUNCH_GONE)
    rig.launch_failures.append(failure)

    page, key = await rig.take()

    assert len(rig.launched) == 1
    await rig.pool.release_page(page, key)
    rig.assert_conserved()


async def test_concurrent_acquisitions_on_a_dead_driver_share_one_new_browser(rig: Rig) -> None:
    rig.pool._browsers.append(_dead_instance())

    held = await asyncio.gather(*[rig.take() for _ in range(6)])

    assert len(rig.launched) == 1
    assert rig.pool._browsers == rig.launched
    assert rig.pool._crash_count_browser == 1, "the dead browser is evicted once, however many callers noticed"
    for page, key in held:
        await rig.pool.release_page(page, key)
    rig.assert_conserved()


async def test_a_cancelled_tick_never_strands_the_permits_of_browsers_it_has_not_closed_yet(
    rig: Rig, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The on-demand tick runs inside the acquiring task, so a Stop can cancel it between two closes."""
    for _ in range(2):
        dead = _dead_instance()
        dead.load = 1  # a page of it is held, and the page holds a permit
        rig.pool._browsers.append(dead)
        await rig.pool._global_semaphore.acquire()
    rig.pool._current_pages_in_use = 2
    closing = asyncio.Event()

    async def close_forever(_inst: BrowserInstance) -> None:
        closing.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(rig.pool, "_close_browser_instance", close_forever)
    tick = asyncio.ensure_future(rig.pool._lifecycle_tick())
    await asyncio.wait_for(closing.wait(), timeout=_BOUND_S)

    tick.cancel()
    with pytest.raises(asyncio.CancelledError):
        await tick

    rig.assert_conserved()
