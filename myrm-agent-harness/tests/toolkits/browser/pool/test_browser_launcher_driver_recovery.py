"""A launcher whose Playwright driver died starts a new driver instead of failing on the dead one forever.

The driver is the Node process every launched browser hangs off. Once it is gone, each call on the cached
`Playwright` fails with "Connection closed while reading from the driver", and nothing but a new driver can launch
a browser again or connect to one.
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator, Iterator
from contextlib import AbstractContextManager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from myrm_agent_harness.toolkits.browser.exceptions import BrowserLaunchError
from myrm_agent_harness.toolkits.browser.pool.browser_launcher import BrowserLauncher

_DRIVER_GONE = "BrowserType.launch: Connection closed while reading from the driver"
_CONNECT_DRIVER_GONE = "BrowserType.connect_over_cdp: Connection closed while reading from the driver"
_CDP_ENDPOINT = "http://127.0.0.1:9222"
_PROMPT_GUARD = "myrm_agent_harness.toolkits.browser.pool.chrome_prompt_guard.watch_chrome_remote_debugging_prompt"


def _driver(launch: AsyncMock) -> MagicMock:
    driver = MagicMock()
    driver.chromium.launch = launch
    driver.stop = AsyncMock()
    return driver


def _dead_driver() -> MagicMock:
    return _driver(AsyncMock(side_effect=Exception(_DRIVER_GONE)))


def _live_driver(browser: MagicMock) -> MagicMock:
    return _driver(AsyncMock(return_value=browser))


def _start_drivers(*drivers: MagicMock) -> AbstractContextManager[MagicMock]:
    """`async_playwright().start()` hands out these drivers in order and fails once they run out."""
    pending = iter(drivers)

    async def start() -> MagicMock:
        return next(pending)

    return patch("patchright.async_api.async_playwright", return_value=MagicMock(start=start))


def _launcher() -> BrowserLauncher:
    return BrowserLauncher(launch_options={"headless": True})


def _connecting_driver(connect: AsyncMock) -> MagicMock:
    driver = MagicMock()
    driver.chromium.connect_over_cdp = connect
    driver.stop = AsyncMock()
    return driver


@contextlib.asynccontextmanager
async def _no_prompt_guard(timeout: float = 4.0) -> AsyncIterator[None]:
    """The real guard polls System Events on macOS, and a mocked connect has no dialog to approve."""
    yield


@contextlib.contextmanager
def _cdp_connect_env(*drivers: MagicMock) -> Iterator[None]:
    with (
        _start_drivers(*drivers),
        patch("asyncio.sleep", new_callable=AsyncMock),
        patch(_PROMPT_GUARD, _no_prompt_guard),
    ):
        yield


async def test_a_dead_driver_is_replaced_and_the_launch_succeeds() -> None:
    browser = MagicMock()
    dead, live = _dead_driver(), _live_driver(browser)
    launcher = _launcher()

    with _start_drivers(dead, live), patch("asyncio.sleep", new_callable=AsyncMock):
        instance = await launcher._launch_new_browser()

    assert instance.browser is browser
    dead.stop.assert_awaited_once()
    live.stop.assert_not_awaited()
    assert launcher._playwright is live


async def test_a_launch_failure_that_is_not_a_dead_driver_keeps_the_driver() -> None:
    """Dropping a driver that still runs would take every browser launched through it down."""
    driver = _driver(AsyncMock(side_effect=Exception("Browser closed unexpectedly")))
    launcher = _launcher()

    with (
        _start_drivers(driver),
        patch("asyncio.sleep", new_callable=AsyncMock),
        pytest.raises(BrowserLaunchError, match="after 3 attempts"),
    ):
        await launcher._launch_new_browser()

    assert driver.chromium.launch.await_count == 3
    driver.stop.assert_not_awaited()
    assert launcher._playwright is driver


async def test_a_driver_that_dies_on_every_attempt_leaves_no_cached_driver() -> None:
    dead = [_dead_driver() for _ in range(3)]
    launcher = _launcher()

    with (
        _start_drivers(*dead),
        patch("asyncio.sleep", new_callable=AsyncMock),
        pytest.raises(BrowserLaunchError, match="after 3 attempts"),
    ):
        await launcher._launch_new_browser()

    for driver in dead:
        driver.stop.assert_awaited_once()
    assert launcher._playwright is None

    browser = MagicMock()
    with _start_drivers(_live_driver(browser)):
        instance = await launcher._launch_new_browser()
    assert instance.browser is browser


async def test_a_dead_driver_that_cannot_be_stopped_is_still_replaced() -> None:
    browser = MagicMock()
    dead, live = _dead_driver(), _live_driver(browser)
    dead.stop = AsyncMock(side_effect=RuntimeError("transport already closed"))
    launcher = _launcher()

    with _start_drivers(dead, live), patch("asyncio.sleep", new_callable=AsyncMock):
        instance = await launcher._launch_new_browser()

    assert instance.browser is browser
    assert launcher._playwright is live


async def test_the_cache_is_cleared_before_the_old_driver_finishes_stopping() -> None:
    """A caller that arrives while the old driver is stopping must start a new one, not pick up the old."""
    launcher = _launcher()
    driver = _live_driver(MagicMock())
    cached_while_stopping: list[object] = []

    async def stop() -> None:
        cached_while_stopping.append(launcher._playwright)

    driver.stop = stop
    with _start_drivers(driver):
        await launcher._ensure_playwright()
    await launcher._discard_playwright()

    assert cached_while_stopping == [None]


async def test_shutdown_stops_and_forgets_the_driver() -> None:
    driver = _live_driver(MagicMock())
    launcher = _launcher()
    with _start_drivers(driver):
        await launcher._ensure_playwright()

    await launcher.shutdown()

    driver.stop.assert_awaited_once()
    assert launcher._playwright is None


async def test_a_cdp_connect_on_a_dead_driver_is_replayed_on_a_new_driver() -> None:
    browser = MagicMock(contexts=[])
    dead = _connecting_driver(AsyncMock(side_effect=Exception(_CONNECT_DRIVER_GONE)))
    live = _connecting_driver(AsyncMock(return_value=browser))
    launcher = _launcher()

    with _cdp_connect_env(dead, live):
        instance = await launcher._connect_existing(_CDP_ENDPOINT)

    assert instance.browser is browser
    assert instance.is_managed is False
    dead.stop.assert_awaited_once()
    live.chromium.connect_over_cdp.assert_awaited_once_with(_CDP_ENDPOINT, headers=None)
    live.stop.assert_not_awaited()
    assert launcher._playwright is live


async def test_a_cdp_connect_failure_that_is_not_a_dead_driver_keeps_the_driver() -> None:
    """Dropping a driver that still runs would take every browser connected through it down."""
    driver = _connecting_driver(AsyncMock(side_effect=ConnectionError("connection refused")))
    launcher = _launcher()

    with _cdp_connect_env(driver), pytest.raises(BrowserLaunchError, match="after 3 attempts"):
        await launcher._connect_existing(_CDP_ENDPOINT)

    assert driver.chromium.connect_over_cdp.await_count == 3
    driver.stop.assert_not_awaited()
    assert launcher._playwright is driver


async def test_a_cdp_connect_whose_driver_dies_on_every_attempt_leaves_no_cached_driver() -> None:
    dead = [_connecting_driver(AsyncMock(side_effect=Exception(_CONNECT_DRIVER_GONE))) for _ in range(3)]
    launcher = _launcher()

    with _cdp_connect_env(*dead), pytest.raises(BrowserLaunchError, match="after 3 attempts"):
        await launcher._connect_existing(_CDP_ENDPOINT)

    for driver in dead:
        driver.stop.assert_awaited_once()
    assert launcher._playwright is None
