"""The extension and its bridge in a real Chromium: connection, tab visibility, authorization, pause.

[INPUT]
- tests.support.extension_real_browser::real_extension_stack (POS: the unpacked extension, the production bridge routes
  and a login-gated fixture site, all real)
- app.services.extension.bridge::ExtensionBridgeNotAvailable (POS: the bridge's refusal)

[OUTPUT]
- the extension's observable contract with the server: handshake identity, which tabs the Agent can see, what happens
  when a domain is authorized or revoked, which navigations the extension refuses on its own, and what pausing does

[POS]
The safety net under every change to the extension and its bridge: the unit tests mock the browser, so only these
tests notice when the extension's own files stop doing what the server expects of them.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from app.services.extension.bridge import ExtensionBridgeNotAvailable
from tests.support.extension_real_browser import (
    INTRANET_HOST,
    OTHER_HOST,
    RealExtensionStack,
    real_extension_stack,
    wait_until,
)

pytestmark = pytest.mark.e2e


@pytest.fixture
async def stack(tmp_path: Path) -> AsyncIterator[RealExtensionStack]:
    async with real_extension_stack(tmp_path / "profile") as running:
        yield running


async def _log_in(stack: RealExtensionStack, host: str) -> None:
    await stack.browser.open_user_tab(stack.site.url(host, "/login?user=alice"))


async def test_popup_connect_completes_the_handshake(stack: RealExtensionStack) -> None:
    status = await stack.bridge.get_status()

    assert status.connected
    assert status.handshake_ready
    assert status.extension_version == stack.browser.version
    assert status.browser_name == "Chrome"
    assert {"navigate_url", "list_tabs", "attach_debugger", "detach_debugger"} <= set(status.capabilities)


async def test_agent_sees_only_tabs_on_authorized_domains(stack: RealExtensionStack) -> None:
    await _log_in(stack, INTRANET_HOST)
    await _log_in(stack, OTHER_HOST)

    await stack.authorize([INTRANET_HOST])

    tabs = await stack.bridge.list_tabs()
    assert [tab.domain for tab in tabs] == [INTRANET_HOST]
    assert tabs[0].url.startswith(stack.site.url(INTRANET_HOST))


async def test_revoking_the_domain_hides_its_tabs_again(stack: RealExtensionStack) -> None:
    await _log_in(stack, INTRANET_HOST)
    await stack.authorize([INTRANET_HOST])
    assert len(await stack.bridge.list_tabs()) == 1

    await stack.authorize([])

    assert await stack.bridge.list_tabs() == []


async def test_foreground_navigation_runs_in_the_users_tab_and_other_domains_are_refused(
    stack: RealExtensionStack,
) -> None:
    await _log_in(stack, INTRANET_HOST)
    await stack.authorize([INTRANET_HOST])

    tab = await stack.bridge.navigate_to_url(stack.site.url(INTRANET_HOST, "/secret"), background=False)

    assert tab.domain == INTRANET_HOST
    assert tab.title == "Secret"  # the session cookie of the user's profile reached the page

    refused = stack.site.url(OTHER_HOST, "/secret")
    with pytest.raises(ExtensionBridgeNotAvailable, match="not authorized"):
        await stack.bridge.navigate_to_url(refused, background=False)


async def test_extension_refuses_an_unauthorized_navigation_even_when_the_server_asks(stack: RealExtensionStack) -> None:
    await stack.authorize([INTRANET_HOST])
    target = stack.site.url(OTHER_HOST, "/secret")

    with pytest.raises(ExtensionBridgeNotAvailable):
        await stack.bridge._send_request("navigate_url", {"url": target, "domain": OTHER_HOST, "background": True}, timeout=10.0)

    assert not any(url.startswith(target) for url in stack.browser.user_tab_urls())


async def test_paused_tab_leaves_the_agent_view_until_resumed(stack: RealExtensionStack) -> None:
    await _log_in(stack, INTRANET_HOST)
    await stack.authorize([INTRANET_HOST])
    (tab,) = await stack.bridge.list_tabs()

    paused = await stack.browser.send({"type": "toggle_pause_tab", "tabId": tab.tab_id})
    assert paused == {"ok": True, "paused": True}

    async def hidden() -> bool:
        return await stack.bridge.list_tabs() == []

    await wait_until(hidden, "the paused tab to leave the Agent's view")

    resumed = await stack.browser.send({"type": "toggle_pause_tab", "tabId": tab.tab_id})
    assert resumed == {"ok": True, "paused": False}
    assert [visible.tab_id for visible in await stack.bridge.list_tabs()] == [tab.tab_id]
