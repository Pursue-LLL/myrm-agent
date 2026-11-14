"""Which authorized sites and paused tabs hold when the extension and the server meet: a server restart, a reconnect, a slow server.

[INPUT]
- conftest::stack (POS: the unpacked extension connected to the production bridge, plus a login-gated fixture site)
- tests.support.extension_real_browser (POS: server restart, the policy the extension holds, what the Agent can see)

[OUTPUT]
- the guarantees about the access policy across connections: a restarted server takes over what the extension kept
  instead of wiping it (authorized sites and paused tabs alike), a policy the user set on the server is what both sides
  hold after the extension returns, and a policy set right after connecting survives the extension's first report

[POS]
Each side keeps a copy of the policy and both copies cross when they connect, so what the user ends up with depends on
which side adopts which message. Only the real extension over a real WebSocket shows the outcome on both sides.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from app.services.extension.bridge import ExtensionBridgeService
from tests.support.extension_real_browser import (
    INTRANET_HOST,
    OTHER_HOST,
    RealExtensionStack,
    real_extension_stack,
    wait_until,
)

pytestmark = pytest.mark.e2e

# How long the slow server takes over each message it reads from the extension.
_SLOW_SERVER_DELAY_S = 0.5


@pytest.fixture
async def stack_with_a_slow_server(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[RealExtensionStack]:
    """A server that is slow to get through what the extension sends right after it connects."""
    sync_relay_tabs = ExtensionBridgeService._sync_relay_tabs

    async def slowly(self: ExtensionBridgeService) -> None:
        await asyncio.sleep(_SLOW_SERVER_DELAY_S)
        await sync_relay_tabs(self)

    monkeypatch.setattr(ExtensionBridgeService, "_sync_relay_tabs", slowly)
    async with real_extension_stack(tmp_path / "profile") as running:
        yield running


async def _settled_tab_ids(stack: RealExtensionStack, host: str) -> list[int]:
    """The ids of the tabs on `host` the Agent can see, once both sides are done with what they sent at connection time.

    The extension handles what the server sent before a request ahead of that request, and the server reads what the
    extension sent before its reply ahead of the reply: a tab listing is a round trip that orders both.
    """
    return [tab.tab_id for tab in await stack.bridge.list_tabs() if tab.domain == host]


async def test_a_restarted_server_takes_over_the_authorized_sites_the_extension_kept(stack: RealExtensionStack) -> None:
    await stack.log_in(INTRANET_HOST)
    await stack.authorize([INTRANET_HOST])

    await stack.restart_server()

    assert await _settled_tab_ids(stack, INTRANET_HOST), "the Agent cannot see the signed-in tab after the restart"
    assert stack.bridge.get_authorized_domains() == [INTRANET_HOST]
    assert (await stack.browser.access_policy())["authorizedDomains"] == [INTRANET_HOST]


async def test_a_tab_the_user_paused_stays_paused_when_the_server_restarts(stack: RealExtensionStack) -> None:
    await stack.log_in(INTRANET_HOST)
    await stack.authorize([INTRANET_HOST])
    (tab_id,) = await _settled_tab_ids(stack, INTRANET_HOST)
    assert (await stack.browser.send({"type": "toggle_pause_tab", "tabId": tab_id}))["paused"] is True

    await stack.restart_server()

    await _settled_tab_ids(stack, INTRANET_HOST)
    assert stack.bridge.get_access_policy().paused_tab_ids == frozenset({tab_id})
    assert (await stack.browser.access_policy())["pausedTabIds"] == [tab_id]


async def test_a_policy_set_on_the_server_while_the_extension_was_away_is_what_both_hold_when_it_returns(
    stack: RealExtensionStack,
) -> None:
    await stack.authorize([INTRANET_HOST])
    assert (await stack.browser.send({"type": "disconnect"})) == {"ok": True}
    await wait_until(stack.disconnected, "the server to see the manual disconnect")
    await stack.bridge.set_authorized_domains([OTHER_HOST])

    await stack.browser.send({"type": "connect"})
    await wait_until(stack.handshaken, "the extension to reconnect when asked to")

    await _settled_tab_ids(stack, OTHER_HOST)
    assert stack.bridge.get_authorized_domains() == [OTHER_HOST]
    assert (await stack.browser.access_policy())["authorizedDomains"] == [OTHER_HOST]


async def test_a_policy_set_right_after_connecting_survives_the_extensions_first_report(
    stack_with_a_slow_server: RealExtensionStack,
) -> None:
    stack = stack_with_a_slow_server
    await stack.authorize([INTRANET_HOST])

    await _settled_tab_ids(stack, INTRANET_HOST)

    assert stack.bridge.get_authorized_domains() == [INTRANET_HOST]
    assert (await stack.browser.access_policy())["authorizedDomains"] == [INTRANET_HOST]
