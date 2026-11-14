"""Which side's access policy holds once the extension connects.

[INPUT]
- app.services.extension.bridge::ExtensionBridgeService (POS: the receive loop that reads the extension's connect-time
  messages and the policy it holds or pushes)
- tests.support.extension_fake_socket::FakeWs (POS: the extension's side of the WebSocket)

[OUTPUT]
- the rule for the policy the extension reports right after `hello`: a server the user never set a policy on adopts it,
  a server the user did set one on pushes its own and ignores that stale copy, and edits reported later always count

[POS]
The extension keeps its policy across server restarts; the server keeps its policy only in memory. Which of the two
copies wins at connection time decides whether a restart wipes the user's authorized sites and paused tabs.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.extension.bridge import ExtensionBridgeService
from tests.support.extension_fake_socket import FakeWs

_HELLO: dict[str, object] = {"type": "hello", "version": "1.0", "browser": "chrome", "capabilities": ["list_tabs"]}


def _report(domains: list[str], *, initial: bool, paused: list[int] | None = None) -> dict[str, object]:
    return {
        "type": "access_policy_update",
        "allow_all_eligible_tabs": False,
        "domains": domains,
        "paused_tab_ids": paused or [],
        "initial": initial,
    }


async def _connect(bridge: ExtensionBridgeService, *frames: dict[str, object]) -> list[dict[str, object]]:
    """Run the receive loop over what the extension sends once it connects; return what the server pushed to it."""
    ws = FakeWs([json.dumps(frame) for frame in frames])
    bridge._connected = True
    bridge._ws = ws
    relay = MagicMock()
    relay.bind_extension_transport = AsyncMock()
    with patch("app.services.extension.bridge.common.get_cdp_relay_manager", return_value=relay):
        await bridge._receive_loop()
    return [json.loads(text) for text in ws.sent]


def _pushed_domains(pushed: list[dict[str, object]]) -> list[object]:
    """The domain list of every policy the server pushed, in order."""
    return [msg["domains"] for msg in pushed if msg["type"] == "set_access_policy"]


async def test_a_server_without_a_policy_of_its_own_adopts_the_one_the_extension_saved() -> None:
    bridge = ExtensionBridgeService()

    pushed = await _connect(bridge, _HELLO, _report(["saved.example"], initial=True, paused=[7]))

    assert bridge.get_authorized_domains() == ["saved.example"]
    assert bridge.get_access_policy().paused_tab_ids == frozenset({7})
    assert pushed == []


async def test_a_server_whose_user_set_a_policy_pushes_it_and_ignores_the_copy_saved_before_connecting() -> None:
    bridge = ExtensionBridgeService()
    await bridge.set_access_policy(authorized_domains=["mine.example"], paused_tab_ids=[3])

    pushed = await _connect(bridge, _HELLO, _report(["saved.example"], initial=True, paused=[7]))

    assert bridge.get_authorized_domains() == ["mine.example"]
    assert bridge.get_access_policy().paused_tab_ids == frozenset({3})
    assert _pushed_domains(pushed) == [["mine.example"]]


async def test_a_policy_the_user_cleared_is_still_the_one_the_user_set() -> None:
    bridge = ExtensionBridgeService()
    await bridge.set_access_policy(authorized_domains=[])

    pushed = await _connect(bridge, _HELLO, _report(["saved.example"], initial=True))

    assert bridge.get_authorized_domains() == []
    assert _pushed_domains(pushed) == [[]]


async def test_an_edit_reported_after_connecting_always_counts() -> None:
    bridge = ExtensionBridgeService()
    await bridge.set_access_policy(authorized_domains=["mine.example"])

    await _connect(
        bridge,
        _HELLO,
        _report(["saved.example"], initial=True),
        _report(["edited.example"], initial=False),
    )

    assert bridge.get_authorized_domains() == ["edited.example"]


async def test_a_report_without_the_initial_marker_is_an_edit() -> None:
    bridge = ExtensionBridgeService()
    await bridge.set_access_policy(authorized_domains=["mine.example"])

    await _connect(bridge, _HELLO, {"type": "access_policy_update", "domains": ["edited.example"]})

    assert bridge.get_authorized_domains() == ["edited.example"]


async def test_the_server_pushes_the_policy_as_the_extension_last_edited_it_at_the_next_connection() -> None:
    bridge = ExtensionBridgeService()
    await bridge.set_access_policy(authorized_domains=["mine.example"])
    await _connect(bridge, _HELLO, _report(["mine.example", "added.example"], initial=False))

    pushed = await _connect(bridge, _HELLO, _report(["stale.example"], initial=True))

    assert _pushed_domains(pushed) == [["mine.example", "added.example"]]
