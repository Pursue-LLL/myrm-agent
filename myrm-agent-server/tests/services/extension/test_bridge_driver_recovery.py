"""The extension bridge keeps no dead Playwright driver around.

The bridge owns a Playwright driver of its own (a Node process), separate from the browser pool's. When that process
exits, every later CDP connect fails with the same message, so a cached handle would fail forever unless the bridge
drops it. These tests use the one thing patchright reports for that failure (`patchright/_impl/_transport.py`).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from myrm_agent_harness.toolkits.browser.pool.extension_bridge import ExtensionBrowserInstance

from app.services.extension.bridge import ExtensionBridgeService
from app.services.extension.bridge.common import RELAY_CAPABILITY

_DRIVER_EXIT_MESSAGE = "BrowserType.connect_over_cdp: Connection closed while reading from the driver"


class _FakeDriver:
    """A Playwright driver handle: the bridge only calls ``chromium.connect_over_cdp`` and ``stop``."""

    def __init__(self, connect: AsyncMock) -> None:
        self.chromium = MagicMock()
        self.chromium.connect_over_cdp = connect
        self.stop = AsyncMock()


def _browser() -> MagicMock:
    browser = MagicMock()
    browser.contexts = []
    return browser


def _drivers_started_in_order(*drivers: _FakeDriver) -> MagicMock:
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
        patch("app.services.extension.bridge.common.get_cdp_relay_manager") as manager,
    ):
        manager.return_value = AsyncMock()
        yield service


async def test_a_connect_that_fails_on_an_exited_driver_leaves_the_next_one_a_new_driver(
    bridge: ExtensionBridgeService,
) -> None:
    dead = _FakeDriver(AsyncMock(side_effect=Exception(_DRIVER_EXIT_MESSAGE)))
    live = _FakeDriver(AsyncMock(return_value=_browser()))
    factory = _drivers_started_in_order(dead, live)

    with patch("patchright.async_api.async_playwright", factory):
        with pytest.raises(Exception, match="Connection closed while reading from the driver"):
            await bridge.connect()
        assert bridge._playwright is None
        dead.stop.assert_awaited_once()

        instance = await bridge.connect()

    assert isinstance(instance, ExtensionBrowserInstance)
    assert factory.call_count == 2
    assert bridge._playwright is live
    live.stop.assert_not_awaited()


async def test_a_connect_that_fails_for_another_reason_keeps_the_driver(bridge: ExtensionBridgeService) -> None:
    driver = _FakeDriver(AsyncMock(side_effect=[TimeoutError("CDP connect timed out"), _browser()]))
    factory = _drivers_started_in_order(driver)

    with patch("patchright.async_api.async_playwright", factory):
        with pytest.raises(TimeoutError):
            await bridge.connect()
        assert bridge._playwright is driver
        await bridge.connect()

    assert factory.call_count == 1
    driver.stop.assert_not_awaited()


async def test_only_the_driver_that_failed_is_dropped(bridge: ExtensionBridgeService) -> None:
    newer = _FakeDriver(AsyncMock(return_value=_browser()))

    async def fail_after_a_newer_driver_took_over(*args: object, **kwargs: object) -> MagicMock:
        bridge._playwright = newer  # type: ignore[assignment]
        raise Exception(_DRIVER_EXIT_MESSAGE)

    dead = _FakeDriver(AsyncMock(side_effect=fail_after_a_newer_driver_took_over))
    factory = _drivers_started_in_order(dead)

    with patch("patchright.async_api.async_playwright", factory):
        with pytest.raises(Exception, match="Connection closed while reading from the driver"):
            await bridge.connect()

    assert bridge._playwright is newer
    newer.stop.assert_not_awaited()
