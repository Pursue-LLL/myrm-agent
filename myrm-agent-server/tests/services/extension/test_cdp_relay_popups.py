"""A page the Agent's page opens (window.open, a target=_blank link) is handed to the Agent like any other page.

Chrome's auto-attach announces a new target to every client that has its opener. The extension reports the tabs an
Agent tab opened with the tab that opened them, and the relay has to announce those the same way: otherwise the click
that opened the page leads somewhere the Agent cannot see. Playwright turns the announcement's openerId into the
page's popup event.
"""

from __future__ import annotations

import asyncio
import gc

import pytest

from app.services.extension.cdp_relay import targets
from app.services.extension.cdp_relay.bridge import ExtensionCdpRelayBridge
from app.services.extension.cdp_relay.protocol import BROWSER_CONTEXT_ID, RelayTabInfo
from tests.support.cdp_relay_fakes import AUTO_ATTACH, FakeExtension, RelayClient, auto_attaching_client, settle

OPENER_TAB = 101  # the first tab FakeExtension opens
POPUP_TAB = 102
OPENER_TARGET = "target-101"
POPUP_TARGET = "target-102"


@pytest.fixture
def extension() -> FakeExtension:
    return FakeExtension()


@pytest.fixture
def bridge(extension: FakeExtension) -> ExtensionCdpRelayBridge:
    relay = ExtensionCdpRelayBridge()
    relay.set_extension_transport(extension)
    return relay


def _opener() -> RelayTabInfo:
    return RelayTabInfo(tab_id=OPENER_TAB, url="https://intranet.example/portal", title="Portal", active=True)


def _opened(
    tab_id: int = POPUP_TAB, opener: int | None = OPENER_TAB, url: str = "https://intranet.example/orders"
) -> RelayTabInfo:
    return RelayTabInfo(tab_id=tab_id, url=url, title="Orders", active=True, opener_tab_id=opener)


@pytest.mark.asyncio
async def test_a_page_opened_by_the_agents_page_is_announced_with_its_opener(
    bridge: ExtensionCdpRelayBridge, extension: FakeExtension
) -> None:
    client = await auto_attaching_client(bridge)

    bridge.sync_tabs([_opener(), _opened()])
    await settle(bridge)

    popup = client.announced()[POPUP_TARGET]
    assert popup["openerId"] == OPENER_TARGET
    assert popup["url"] == "https://intranet.example/orders"
    assert popup["browserContextId"] == BROWSER_CONTEXT_ID
    assert extension.attached_tab_ids() == [OPENER_TAB, POPUP_TAB]


@pytest.mark.asyncio
async def test_the_page_is_announced_once_however_often_the_tab_list_repeats_it(bridge: ExtensionCdpRelayBridge) -> None:
    client = await auto_attaching_client(bridge)

    bridge.sync_tabs([_opener(), _opened()])
    await settle(bridge)
    bridge.sync_tabs([_opener(), _opened(url="https://intranet.example/orders?page=2")])
    await settle(bridge)

    announcements = [frame for frame in client.frames if frame.get("method") == "Target.attachedToTarget"]
    assert len(announcements) == 2  # the opener and the popup, each once: Playwright refuses a target it already has
    listed = (await client.call("Target.getTargets")).result["targetInfos"]
    assert isinstance(listed, list)
    assert {info["targetId"]: info.get("openerId") for info in listed} == {OPENER_TARGET: None, POPUP_TARGET: OPENER_TARGET}


@pytest.mark.asyncio
async def test_a_page_reported_before_its_opener_is_known_is_handed_over_once_the_opener_is_named(
    bridge: ExtensionCdpRelayBridge, extension: FakeExtension
) -> None:
    client = await auto_attaching_client(bridge)

    bridge.sync_tabs([_opener(), _opened(opener=None)])
    await settle(bridge)
    assert extension.attached_tab_ids() == [OPENER_TAB]  # nothing says the Agent's page opened it yet

    bridge.sync_tabs([_opener(), _opened()])
    await settle(bridge)

    assert extension.attached_tab_ids() == [OPENER_TAB, POPUP_TAB]
    assert client.announced()[POPUP_TARGET]["openerId"] == OPENER_TARGET


@pytest.mark.asyncio
async def test_the_page_joins_the_virtual_context_of_its_opener_and_closes_with_it(
    bridge: ExtensionCdpRelayBridge, extension: FakeExtension
) -> None:
    client = RelayClient(bridge)
    await client.call("Target.setAutoAttach", AUTO_ATTACH)
    context_id = await client.create_context()
    await client.create_page(context_id)

    bridge.sync_tabs([_opener(), _opened()])
    await settle(bridge)

    assert client.announced_contexts() == {OPENER_TARGET: context_id, POPUP_TARGET: context_id}
    await client.call("Target.disposeBrowserContext", {"browserContextId": context_id})
    assert extension.closed_tab_ids() == [OPENER_TAB, POPUP_TAB]


@pytest.mark.asyncio
async def test_a_page_opened_by_an_opened_page_is_announced_too(bridge: ExtensionCdpRelayBridge) -> None:
    client = await auto_attaching_client(bridge)
    bridge.sync_tabs([_opener(), _opened()])
    await settle(bridge)

    bridge.sync_tabs([_opener(), _opened(), _opened(tab_id=103, opener=POPUP_TAB, url="https://intranet.example/receipt")])
    await settle(bridge)

    assert client.announced()["target-103"]["openerId"] == POPUP_TARGET


@pytest.mark.asyncio
async def test_every_client_that_has_the_opener_is_told_and_one_that_does_not_is_not(
    bridge: ExtensionCdpRelayBridge,
) -> None:
    owner = await auto_attaching_client(bridge)
    second_agent = RelayClient(bridge)
    await second_agent.call("Target.setAutoAttach", AUTO_ATTACH)  # announces the owner's page to it as well
    bystander = RelayClient(bridge)  # never asked for auto-attach

    bridge.sync_tabs([_opener(), _opened()])
    await settle(bridge)

    assert POPUP_TARGET in owner.announced()
    assert POPUP_TARGET in second_agent.announced()
    assert bystander.announced() == {}


@pytest.mark.asyncio
async def test_a_page_nobody_opened_is_not_handed_to_the_client(
    bridge: ExtensionCdpRelayBridge, extension: FakeExtension
) -> None:
    client = await auto_attaching_client(bridge)

    bridge.sync_tabs([_opener(), _opened(opener=None)])
    await settle(bridge)

    assert POPUP_TARGET not in client.announced()
    assert extension.attached_tab_ids() == [OPENER_TAB]


@pytest.mark.asyncio
async def test_a_page_whose_opener_is_not_attached_is_not_handed_to_anyone(
    bridge: ExtensionCdpRelayBridge, extension: FakeExtension
) -> None:
    client = RelayClient(bridge)
    await client.call("Target.setAutoAttach", AUTO_ATTACH)

    bridge.sync_tabs([_opener(), _opened()])
    await settle(bridge)

    assert extension.attached_tab_ids() == []
    assert client.announced() == {}


@pytest.mark.asyncio
async def test_a_page_the_extension_cannot_attach_is_left_out_without_breaking_the_client(
    bridge: ExtensionCdpRelayBridge, extension: FakeExtension, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = await auto_attaching_client(bridge)
    extension.attach_fails_with = "debugger busy"
    warnings: list[str] = []
    # Formatted on the spot: a log record keeps its arguments, and a failure among them, alive.
    monkeypatch.setattr(targets.logger, "warning", lambda message, *args: warnings.append(message % args))
    unhandled: list[str] = []  # what asyncio logs as an error nobody asked for
    asyncio.get_running_loop().set_exception_handler(lambda _loop, context: unhandled.append(str(context["message"])))

    bridge.sync_tabs([_opener(), _opened()])
    await settle(bridge)
    gc.collect()

    assert POPUP_TARGET not in client.announced()
    assert warnings == ["Could not attach tab 102 opened by tab 101: debugger busy"]
    assert unhandled == []
    assert (await client.call("Target.getTargets")).result["targetInfos"]  # the client still gets answers


@pytest.mark.asyncio
async def test_the_client_is_told_when_the_page_goes_away(bridge: ExtensionCdpRelayBridge) -> None:
    client = await auto_attaching_client(bridge)
    bridge.sync_tabs([_opener(), _opened()])
    await settle(bridge)

    bridge.sync_tabs([_opener()])

    assert client.detached_targets() == [POPUP_TARGET]
