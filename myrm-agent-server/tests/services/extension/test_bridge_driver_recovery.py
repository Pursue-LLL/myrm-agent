"""The extension bridge keeps no dead Playwright driver around.

The bridge owns a Playwright driver of its own (a Node process), separate from the browser pool's. When that process
exits, every CDP connect on it fails with the same message, so the bridge drops the dead driver and attaches again on
a new one within the same call. These tests use the one thing patchright reports for that failure
(`patchright/_impl/_transport.py`).
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from myrm_agent_harness.toolkits.browser.pool.extension_bridge import ExtensionBrowserInstance

from app.services.extension.bridge import ExtensionBridgeService
from app.services.extension.bridge.common import RELAY_CAPABILITY

_DRIVER_EXIT_MESSAGE = "BrowserType.connect_over_cdp: Connection closed while reading from the driver"


def _driver(connect: AsyncMock) -> MagicMock:
    """A Playwright driver handle: the bridge only calls ``chromium.connect_over_cdp`` and ``stop``."""
    driver = MagicMock()
    driver.chromium.connect_over_cdp = connect
    driver.stop = AsyncMock()
    return driver


def _exited_driver() -> MagicMock:
    return _driver(AsyncMock(side_effect=Exception(_DRIVER_EXIT_MESSAGE)))


def _live_driver() -> MagicMock:
    browser = MagicMock()
    browser.contexts = []
    return _driver(AsyncMock(return_value=browser))


def _drivers_started_in_order(*drivers: MagicMock) -> MagicMock:
    """Stand-in for ``async_playwright``: each ``async_playwright().start()`` yields the next driver."""
    queue = list(drivers)
    factory = MagicMock()
    factory.side_effect = lambda: MagicMock(start=AsyncMock(side_effect=lambda: queue.pop(0)))
    return factory


@pytest.fixture
async def bridge() -> AsyncIterator[ExtensionBridgeService]:
    """A bridge whose extension is connected and whose relay endpoint resolves."""
    service = ExtensionBridgeService()
    service._connected = True
    service._ws = MagicMock()
    service._hello_received = True
    service._capabilities = {RELAY_CAPABILITY}
    await service.set_access_policy(allow_all_eligible_tabs=True)

    async def list_tabs(action: str, payload: dict[str, object] | None = None, **kwargs: object) -> object:
        if action == "list_tabs":
            return [{"id": 7, "url": "https://example.com/", "title": "Example", "domain": "example.com", "active": True}]
        return {}

    with (
        patch.object(service, "_resolve_playwright_cdp_endpoint", AsyncMock(return_value="ws://cdp")),
        patch.object(service, "_send_request", side_effect=list_tabs),
        patch.object(service, "_focus_browser_on_domain", AsyncMock()),
        patch("app.services.extension.bridge.common.get_cdp_relay_manager") as manager,
    ):
        manager.return_value = AsyncMock()
        yield service


async def test_a_connect_on_an_exited_driver_is_served_by_a_new_one_in_the_same_call(
    bridge: ExtensionBridgeService,
) -> None:
    dead, live = _exited_driver(), _live_driver()
    factory = _drivers_started_in_order(dead, live)

    with patch("patchright.async_api.async_playwright", factory):
        instance = await bridge.connect()

    assert isinstance(instance, ExtensionBrowserInstance)
    assert factory.call_count == 2
    dead.stop.assert_awaited_once()
    assert bridge._playwright is live
    live.stop.assert_not_awaited()


async def test_connect_to_domain_is_served_by_a_new_driver_the_same_way(bridge: ExtensionBridgeService) -> None:
    dead, live = _exited_driver(), _live_driver()
    factory = _drivers_started_in_order(dead, live)

    with patch("patchright.async_api.async_playwright", factory):
        instance = await bridge.connect_to_domain("example.com")

    assert isinstance(instance, ExtensionBrowserInstance)
    dead.stop.assert_awaited_once()
    assert bridge._playwright is live


async def test_a_new_driver_that_exits_too_ends_the_call_and_is_dropped_as_well(bridge: ExtensionBridgeService) -> None:
    first_dead, second_dead, live = _exited_driver(), _exited_driver(), _live_driver()
    factory = _drivers_started_in_order(first_dead, second_dead, live)

    with patch("patchright.async_api.async_playwright", factory):
        with pytest.raises(Exception, match="Connection closed while reading from the driver"):
            await bridge.connect()

        assert factory.call_count == 2  # one retry, not a loop
        assert bridge._playwright is None
        first_dead.stop.assert_awaited_once()
        second_dead.stop.assert_awaited_once()

        await bridge.connect()

    assert bridge._playwright is live


async def test_a_connect_that_fails_for_another_reason_keeps_the_driver_and_is_not_retried(
    bridge: ExtensionBridgeService,
) -> None:
    driver = _live_driver()
    driver.chromium.connect_over_cdp.side_effect = [TimeoutError("CDP connect timed out"), MagicMock(contexts=[])]
    factory = _drivers_started_in_order(driver)

    with patch("patchright.async_api.async_playwright", factory):
        with pytest.raises(TimeoutError):
            await bridge.connect()
        assert driver.chromium.connect_over_cdp.await_count == 1
        assert bridge._playwright is driver
        await bridge.connect()

    assert factory.call_count == 1
    driver.stop.assert_not_awaited()


async def test_callers_that_arrive_while_a_driver_starts_share_it(bridge: ExtensionBridgeService) -> None:
    live, release = _live_driver(), asyncio.Event()

    async def start_when_released() -> MagicMock:
        await release.wait()
        return live

    factory = MagicMock(side_effect=lambda: MagicMock(start=start_when_released))

    with patch("patchright.async_api.async_playwright", factory):
        callers = asyncio.gather(bridge._ensure_playwright(), bridge._ensure_playwright())
        await asyncio.sleep(0)  # both callers have reached the driver start
        release.set()
        drivers = await callers

    assert list(drivers) == [live, live]
    assert factory.call_count == 1


async def test_connects_that_fail_together_on_an_exited_driver_share_one_new_driver(
    bridge: ExtensionBridgeService,
) -> None:
    both_attached = asyncio.Barrier(2)

    async def exit_once_both_attached(*args: object, **kwargs: object) -> MagicMock:
        await both_attached.wait()
        raise Exception(_DRIVER_EXIT_MESSAGE)

    dead, live = _driver(AsyncMock(side_effect=exit_once_both_attached)), _live_driver()
    bridge._playwright = dead

    async def start_live() -> MagicMock:
        await asyncio.sleep(0)  # a driver takes time to start: the other caller is already waiting for it
        return live

    factory = MagicMock(side_effect=lambda: MagicMock(start=start_live))

    with patch("patchright.async_api.async_playwright", factory):
        instances = await asyncio.gather(bridge.connect(), bridge.connect())

    assert all(isinstance(instance, ExtensionBrowserInstance) for instance in instances)
    assert factory.call_count == 1
    assert bridge._playwright is live
    dead.stop.assert_awaited_once()
    live.stop.assert_not_awaited()


async def test_only_the_driver_that_failed_is_dropped(bridge: ExtensionBridgeService) -> None:
    """Another caller already replaced the failed driver: its newer one keeps serving, and the retry runs on it."""
    newer = _live_driver()

    async def fail_after_a_newer_driver_took_over(*args: object, **kwargs: object) -> MagicMock:
        bridge._playwright = newer
        raise Exception(_DRIVER_EXIT_MESSAGE)

    dead = _driver(AsyncMock(side_effect=fail_after_a_newer_driver_took_over))
    factory = _drivers_started_in_order(dead)

    with patch("patchright.async_api.async_playwright", factory):
        instance = await bridge.connect()

    assert isinstance(instance, ExtensionBrowserInstance)
    assert bridge._playwright is newer
    newer.chromium.connect_over_cdp.assert_awaited_once()
    newer.stop.assert_not_awaited()
    dead.stop.assert_not_awaited()  # whoever replaced it stops it; this caller no longer owns it
