"""A browser the pool cannot close because its driver exited is ended through the driver's token; no other close is.

Closing goes through the driver. When the driver is gone the close fails, and nothing else can reach a browser that
kept running. Any other failure to close (a hung browser, a timeout) is left to the driver and to Browser Doctor: the
pool does not signal processes it merely failed to close.
"""

from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from myrm_agent_harness.toolkits.browser.pool import GlobalBrowserPool
from myrm_agent_harness.toolkits.browser.pool.browser_launcher import BrowserInstance

_REAPER = "myrm_agent_harness.toolkits.browser.pool.pool_lifecycle.terminate_driver_browsers"
_TOKEN = "token-of-the-exited-driver"
_CLOSE_GONE = "Browser.close: Connection closed while reading from the driver"
_PROBE_GONE = "Browser.new_browser_cdp_session: Connection closed while reading from the driver"


@pytest.fixture(autouse=True)
def reaper() -> Iterator[AsyncMock]:
    with patch(_REAPER, new_callable=AsyncMock, return_value=1) as ended:
        yield ended


def _instance(*, close: AsyncMock, token: str | None = _TOKEN, managed: bool = True) -> BrowserInstance:
    browser = MagicMock()
    browser.close = close
    browser.new_browser_cdp_session = AsyncMock(side_effect=Exception(_PROBE_GONE))
    return BrowserInstance(browser=browser, is_managed=managed, driver_token=token)


async def test_a_close_that_fails_on_the_exited_driver_ends_the_browser_under_its_token(reaper: AsyncMock) -> None:
    pool = GlobalBrowserPool(max_browsers=1)

    await pool._close_browser_instance(_instance(close=AsyncMock(side_effect=Exception(_CLOSE_GONE))))

    reaper.assert_awaited_once_with(_TOKEN)


async def test_a_close_that_failed_on_the_exited_driver_through_a_wrapper_is_recognised(reaper: AsyncMock) -> None:
    wrapped = RuntimeError("could not close the browser")
    wrapped.__cause__ = Exception(_CLOSE_GONE)
    pool = GlobalBrowserPool(max_browsers=1)

    await pool._close_browser_instance(_instance(close=AsyncMock(side_effect=wrapped)))

    reaper.assert_awaited_once_with(_TOKEN)


@pytest.mark.parametrize(
    "failure",
    [RuntimeError("Browser closed unexpectedly"), TimeoutError()],
    ids=["a failure that is not the driver's exit", "a close that times out"],
)
async def test_a_close_that_fails_for_another_reason_ends_nothing(reaper: AsyncMock, failure: Exception) -> None:
    pool = GlobalBrowserPool(max_browsers=1)

    await pool._close_browser_instance(_instance(close=AsyncMock(side_effect=failure)))

    reaper.assert_not_awaited()


async def test_a_close_that_succeeds_ends_nothing(reaper: AsyncMock) -> None:
    pool = GlobalBrowserPool(max_browsers=1)

    await pool._close_browser_instance(_instance(close=AsyncMock()))

    reaper.assert_not_awaited()


async def test_a_browser_the_pool_did_not_launch_is_never_ended(reaper: AsyncMock) -> None:
    close = AsyncMock(side_effect=Exception(_CLOSE_GONE))
    pool = GlobalBrowserPool(max_browsers=1)

    await pool._close_browser_instance(_instance(close=close, managed=False))

    close.assert_not_awaited()
    reaper.assert_not_awaited()


async def test_a_browser_without_a_driver_token_is_never_ended(reaper: AsyncMock) -> None:
    pool = GlobalBrowserPool(max_browsers=1)

    await pool._close_browser_instance(_instance(close=AsyncMock(side_effect=Exception(_CLOSE_GONE)), token=None))

    reaper.assert_not_awaited()


async def test_the_lifecycle_tick_that_evicts_a_browser_of_an_exited_driver_ends_it(reaper: AsyncMock) -> None:
    pool = GlobalBrowserPool(max_browsers=1)
    dead = _instance(close=AsyncMock(side_effect=Exception(_CLOSE_GONE)))
    pool._browsers.append(dead)

    await pool._lifecycle_tick()

    assert pool._browsers == []
    reaper.assert_awaited_once_with(_TOKEN)


async def test_shutdown_ends_a_browser_whose_driver_exited(reaper: AsyncMock) -> None:
    pool = GlobalBrowserPool(max_browsers=1)
    pool._browsers.append(_instance(close=AsyncMock(side_effect=Exception(_CLOSE_GONE))))

    await pool.shutdown()

    reaper.assert_awaited_once_with(_TOKEN)
