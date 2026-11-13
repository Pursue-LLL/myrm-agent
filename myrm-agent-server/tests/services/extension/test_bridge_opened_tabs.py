"""The bridge's mirror of the tabs an Agent tab opened, and what it tells the relay about them.

The extension marks the tabs the Agent owns and, for the ones its pages opened, the Agent tab that opened them. The
relay hands the Agent a new page only on that word, so the mirror must keep the opener for Agent tabs, ignore it
everywhere else, and pass it on with the tab list.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.services.extension.bridge import ExtensionBridgeService


async def _tabs_the_relay_is_told_of(bridge: ExtensionBridgeService) -> dict[int, int | None]:
    told: dict[int, int | None] = {}
    with patch("app.services.extension.bridge.common.get_cdp_relay_manager") as mock_manager:
        mock_manager.return_value.sync_tabs_from_extension.side_effect = lambda tabs: told.update(
            {tab.tab_id: tab.opener_tab_id for tab in tabs}
        )
        await bridge._sync_relay_tabs()
    return told


def _tab(tab_id: int, **fields: object) -> dict[str, object]:
    return {"id": tab_id, "url": f"https://example.com/{tab_id}", "domain": "example.com", **fields}


@pytest.mark.asyncio
async def test_an_agent_tab_keeps_the_tab_that_opened_it_and_the_relay_is_told() -> None:
    bridge = ExtensionBridgeService()
    await bridge.set_authorized_domains(["example.com"])

    bridge._apply_tab_list([_tab(1, agentOwned=True, openerTabId=None), _tab(2, agentOwned=True, openerTabId=1)])

    assert bridge._agent_tabs == {1: None, 2: 1}
    assert await _tabs_the_relay_is_told_of(bridge) == {1: None, 2: 1}


@pytest.mark.asyncio
async def test_a_tab_that_is_not_the_agents_never_has_an_opener_on_record() -> None:
    bridge = ExtensionBridgeService()
    await bridge.set_authorized_domains(["example.com"])

    bridge._apply_tab_list([_tab(1, agentOwned=True), _tab(2, openerTabId=1)])

    assert bridge._agent_tabs == {1: None}
    assert await _tabs_the_relay_is_told_of(bridge) == {1: None, 2: None}


@pytest.mark.asyncio
async def test_a_new_page_is_handed_to_the_relay_only_once_it_holds_a_document() -> None:
    bridge = ExtensionBridgeService()
    await bridge.set_authorized_domains(["example.com"])
    blank = _tab(2, agentOwned=True, openerTabId=1, url="")

    bridge._apply_tab_list([_tab(1, agentOwned=True), blank])
    assert await _tabs_the_relay_is_told_of(bridge) == {1: None, 2: None}  # still opening: the relay lists it, nobody gets it

    bridge._apply_tab_list([_tab(1, agentOwned=True), {**blank, "url": "https://example.com/2"}])
    assert await _tabs_the_relay_is_told_of(bridge) == {1: None, 2: 1}


@pytest.mark.parametrize("opener", ["1", 1.5, None, [1]], ids=["string", "float", "null", "list"])
def test_an_opener_that_is_not_a_tab_id_is_ignored(opener: object) -> None:
    bridge = ExtensionBridgeService()

    bridge._apply_tab_list([_tab(2, agentOwned=True, openerTabId=opener)])

    assert bridge._agent_tabs == {2: None}
