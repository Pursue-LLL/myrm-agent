"""The extension's own lifecycle in a real Chromium: background navigation, worker restarts, manual disconnects.

[INPUT]
- conftest::stack (POS: the unpacked extension connected to the production bridge, plus a login-gated fixture site)
- tests.support.extension_real_browser (POS: service-worker termination, extension-page scripts, the Agent's browser)

[OUTPUT]
- the guarantees that hold while nobody is looking: private-URL navigation opens in a window apart from the user's own
  and the Agent's work there never moves the user's focused window or active tab, the extension finds its way back after
  the browser reclaims its service worker, and a disconnect the user asked for is not undone by the reconnect timers

[POS]
A service worker keeps nothing in memory between wake-ups, so each of these behaviours is only observable in a real
browser that really stops the worker; unit tests with a mocked chrome object cannot show that state is recovered.
"""

from __future__ import annotations

import asyncio

import pytest

from tests.support.extension_real_browser import INTRANET_HOST, RealExtensionStack, find_page, new_agent_page, wait_until

pytestmark = pytest.mark.e2e

# Longer than the extension's first reconnect delay, so a reconnect that should not happen has time to happen.
RECONNECT_GRACE_S = 4.5

_WINDOWS_SCRIPT = "async () => (await chrome.windows.getAll({ populate: true })).map((win) => win.tabs.map((tab) => tab.id))"


async def _restart_service_worker(stack: RealExtensionStack) -> None:
    """Stop the worker, then wake it with a message, as opening the popup after the browser reclaimed it does."""
    await stack.browser.stop_service_worker()

    await wait_until(stack.disconnected, "the server to notice that the extension went away")
    await stack.browser.send({"type": "get_status"})


async def test_background_navigation_opens_the_page_in_a_window_apart_from_the_users(stack: RealExtensionStack) -> None:
    await stack.log_in(INTRANET_HOST)
    await stack.authorize([INTRANET_HOST])

    tab = await stack.bridge.navigate_to_url(stack.site.url(INTRANET_HOST, "/secret"), background=True)

    assert tab.title == "Secret"
    windows = await stack.browser.evaluate(_WINDOWS_SCRIPT)
    assert isinstance(windows, list) and len(windows) == 2
    (holding_window,) = [tab_ids for tab_ids in windows if tab.tab_id in tab_ids]
    assert holding_window == [tab.tab_id]


async def test_the_agents_work_in_the_background_window_never_moves_the_users_view(stack: RealExtensionStack) -> None:
    await stack.log_in(INTRANET_HOST)
    await stack.authorize([INTRANET_HOST])
    await stack.bridge.navigate_to_url(stack.site.url(INTRANET_HOST, "/secret"), background=True)
    users_view = await stack.browser.users_view()
    assert "/login" in users_view.active_url and users_view.window_count == 2

    async with stack.agent_browser() as browser:
        page = find_page(browser, "/secret")
        await page.click("#orders-link")
        await page.wait_for_selector("#orders")
        await page.screenshot()
        await page.bring_to_front()  # what the Agent's switch-tab sends

        assert await stack.browser.users_view() == users_view


async def test_the_extension_reconnects_after_its_service_worker_restarts(stack: RealExtensionStack) -> None:
    await _restart_service_worker(stack)

    await wait_until(stack.handshaken, "the restarted extension to reconnect and complete the handshake")

    assert await stack.browser.evaluate("() => chrome.alarms.get('myrm-keepalive').then(Boolean)") is True


async def test_a_manual_disconnect_stays_disconnected_until_the_user_connects_again(stack: RealExtensionStack) -> None:
    assert await stack.browser.send({"type": "disconnect"}) == {"ok": True}
    await wait_until(stack.disconnected, "the server to see the manual disconnect")

    await asyncio.sleep(RECONNECT_GRACE_S)
    assert await stack.disconnected()

    await stack.browser.send({"type": "connect"})
    await wait_until(stack.handshaken, "the extension to reconnect when asked to")


async def test_the_agent_works_again_after_the_service_worker_restarted_under_it(stack: RealExtensionStack) -> None:
    await stack.log_in(INTRANET_HOST)
    await stack.authorize([INTRANET_HOST])

    async with stack.agent_browser() as browser:
        stranded = await new_agent_page(browser)
        await stranded.goto(stack.site.url(INTRANET_HOST, "/secret"))

        await _restart_service_worker(stack)
        await wait_until(stack.handshaken, "the restarted extension to reconnect")

        async def told_the_page_is_gone() -> bool:
            return stranded.is_closed()

        await wait_until(told_the_page_is_gone, "the first session to be told its page is gone")

    async with stack.agent_browser() as browser:
        page = await new_agent_page(browser)
        await page.goto(stack.site.url(INTRANET_HOST, "/secret"))

        assert await page.inner_text("#data") == "private-data-42"
