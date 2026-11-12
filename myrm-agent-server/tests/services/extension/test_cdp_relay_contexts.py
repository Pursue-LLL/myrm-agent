"""Virtual browser contexts and Target.closeTarget in the extension CDP relay.

Playwright's new_context() / new_page() / page.close() / context.close() are built on
Target.createBrowserContext, createTarget(browserContextId), closeTarget and disposeBrowserContext.
The relay serves them over the user's one real browser: a context is an ownership group for the tabs
the Agent opens, not a storage partition.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass

import pytest

from app.services.extension.cdp_relay.bridge import ExtensionCdpRelayBridge
from app.services.extension.cdp_relay.protocol import BROWSER_CONTEXT_ID, RelayTabInfo


class FakeExtension:
    """Stands in for the MV3 extension: records every relay command and answers the way the real one does."""

    def __init__(self) -> None:
        self.commands: list[dict[str, object]] = []
        self.opens_no_tabs_of_its_own = False
        self.close_fails_with: str | None = None
        self._next_tab_id = 100

    async def __call__(self, command: dict[str, object]) -> object:
        self.commands.append(command)
        kind = command["type"]
        if kind == "createTab":
            self._next_tab_id += 1
            return {"tabId": self._next_tab_id}
        if kind == "attach":
            return {"targetId": f"target-{command['tabId']}"}
        if kind == "closeTab":
            if self.close_fails_with is not None:
                raise RuntimeError(self.close_fails_with)
            # The extension closes only tabs the Agent opened and leaves every other tab as the user had it.
            return {"closed": not self.opens_no_tabs_of_its_own}
        return {}

    def closed_tab_ids(self) -> list[object]:
        return sorted(
            (command["tabId"] for command in self.commands if command["type"] == "closeTab"),
            key=str,
        )

    def opened_tabs(self) -> int:
        return sum(1 for command in self.commands if command["type"] == "createTab")

    def detached_tab_ids(self) -> list[object]:
        return [command["tabId"] for command in self.commands if command["type"] == "detach"]


@dataclass(frozen=True)
class Reply:
    payload: dict[str, object]

    @property
    def result(self) -> dict[str, object]:
        result = self.payload.get("result")
        assert isinstance(result, dict), self.payload
        return result

    @property
    def error(self) -> dict[str, object]:
        error = self.payload.get("error")
        assert isinstance(error, dict), self.payload
        return error


class Playwright:
    """A CDP client of the relay: sends requests and keeps every frame the relay answers or announces."""

    def __init__(self, bridge: ExtensionCdpRelayBridge) -> None:
        self.bridge = bridge
        self.frames: list[dict[str, object]] = []
        self._next_id = 1
        self.on_message, self.on_close = bridge.attach_cdp_client(lambda raw: self.frames.append(json.loads(raw)))
        self.client = bridge._clients[-1]

    async def call(self, method: str, params: dict[str, object] | None = None) -> Reply:
        request_id = self._next_id
        self._next_id += 1
        await self.bridge._handle_cdp_client_message(
            self.client, json.dumps({"id": request_id, "method": method, "params": params or {}})
        )
        return Reply(next(frame for frame in reversed(self.frames) if frame.get("id") == request_id))

    async def create_context(self) -> str:
        context_id = (await self.call("Target.createBrowserContext", {"disposeOnDetach": True})).result["browserContextId"]
        assert isinstance(context_id, str)
        return context_id

    async def create_page(self, context_id: str | None = None) -> str:
        params: dict[str, object] = {"url": "about:blank"}
        if context_id is not None:
            params["browserContextId"] = context_id
        target_id = (await self.call("Target.createTarget", params)).result["targetId"]
        assert isinstance(target_id, str)
        return target_id

    def announced_contexts(self) -> dict[str, object]:
        """Target id → browserContextId, as carried by every Target.attachedToTarget the client received."""
        announced: dict[str, object] = {}
        for frame in self.frames:
            if frame.get("method") == "Target.attachedToTarget":
                params = frame["params"]
                assert isinstance(params, dict)
                info = params["targetInfo"]
                assert isinstance(info, dict)
                announced[str(info["targetId"])] = info["browserContextId"]
        return announced

    def detached_targets(self) -> list[object]:
        targets: list[object] = []
        for frame in self.frames:
            if frame.get("method") == "Target.detachedFromTarget":
                params = frame["params"]
                assert isinstance(params, dict)
                targets.append(params["targetId"])
        return targets


@pytest.fixture
def extension() -> FakeExtension:
    return FakeExtension()


@pytest.fixture
def bridge(extension: FakeExtension) -> ExtensionCdpRelayBridge:
    relay = ExtensionCdpRelayBridge()
    relay.set_extension_transport(extension)
    return relay


async def _settle() -> None:
    for _ in range(5):
        await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_create_browser_context_returns_a_fresh_id_each_time(bridge: ExtensionCdpRelayBridge) -> None:
    client = Playwright(bridge)
    first = await client.create_context()
    second = await client.create_context()

    assert first != second
    assert BROWSER_CONTEXT_ID not in (first, second)


@pytest.mark.asyncio
async def test_a_tab_created_in_a_context_reports_that_context(bridge: ExtensionCdpRelayBridge) -> None:
    client = Playwright(bridge)
    context_id = await client.create_context()

    in_context = await client.create_page(context_id)
    in_default = await client.create_page()

    expected = {in_context: context_id, in_default: BROWSER_CONTEXT_ID}
    assert client.announced_contexts() == expected
    listed = (await client.call("Target.getTargets")).result["targetInfos"]
    assert isinstance(listed, list)
    assert {info["targetId"]: info["browserContextId"] for info in listed} == expected


@pytest.mark.asyncio
async def test_create_target_in_an_unknown_context_is_refused_without_opening_a_tab(
    bridge: ExtensionCdpRelayBridge, extension: FakeExtension
) -> None:
    client = Playwright(bridge)
    reply = await client.call("Target.createTarget", {"url": "about:blank", "browserContextId": "myrm-ctx-unknown"})

    assert reply.error["code"] == -32602
    assert extension.opened_tabs() == 0


@pytest.mark.asyncio
async def test_dispose_browser_context_closes_only_its_own_tabs(
    bridge: ExtensionCdpRelayBridge, extension: FakeExtension
) -> None:
    client = Playwright(bridge)
    context_a = await client.create_context()
    context_b = await client.create_context()
    await client.create_page(context_a)
    await client.create_page(context_a)
    await client.create_page(context_b)
    await client.create_page()

    reply = await client.call("Target.disposeBrowserContext", {"browserContextId": context_a})

    assert reply.result == {}
    assert extension.closed_tab_ids() == [101, 102]
    assert sorted(bridge._tabs) == [103, 104]
    assert len(client.detached_targets()) == 2
    again = await client.call("Target.createTarget", {"url": "about:blank", "browserContextId": context_a})
    assert again.error["code"] == -32602


@pytest.mark.asyncio
async def test_dispose_of_an_unknown_context_is_an_error(bridge: ExtensionCdpRelayBridge) -> None:
    client = Playwright(bridge)
    reply = await client.call("Target.disposeBrowserContext", {"browserContextId": "myrm-ctx-unknown"})
    assert reply.error["code"] == -32602


@pytest.mark.asyncio
async def test_dispose_still_forgets_the_context_when_a_tab_cannot_be_closed(
    bridge: ExtensionCdpRelayBridge, extension: FakeExtension
) -> None:
    client = Playwright(bridge)
    context_id = await client.create_context()
    await client.create_page(context_id)
    extension.close_fails_with = "Extension not connected"

    reply = await client.call("Target.disposeBrowserContext", {"browserContextId": context_id})

    assert reply.result == {}
    assert bridge._tabs[101].context_id is None
    again = await client.call("Target.createTarget", {"url": "about:blank", "browserContextId": context_id})
    assert again.error["code"] == -32602


@pytest.mark.asyncio
async def test_dispose_lets_go_of_a_tab_the_extension_keeps_open(
    bridge: ExtensionCdpRelayBridge, extension: FakeExtension
) -> None:
    client = Playwright(bridge)
    context_id = await client.create_context()
    target_id = await client.create_page(context_id)
    extension.opens_no_tabs_of_its_own = True

    reply = await client.call("Target.disposeBrowserContext", {"browserContextId": context_id})

    assert reply.result == {}
    assert extension.detached_tab_ids() == [101]
    assert client.detached_targets() == [target_id]


@pytest.mark.asyncio
async def test_closing_the_client_disposes_the_contexts_it_created(
    bridge: ExtensionCdpRelayBridge, extension: FakeExtension
) -> None:
    owner = Playwright(bridge)
    bystander = Playwright(bridge)
    await owner.create_page(await owner.create_context())
    await bystander.create_page(await bystander.create_context())

    owner.on_close()
    await _settle()

    assert extension.closed_tab_ids() == [101]
    assert sorted(bridge._tabs) == [102]


@pytest.mark.asyncio
async def test_close_target_closes_the_tab_and_announces_the_detach(
    bridge: ExtensionCdpRelayBridge, extension: FakeExtension
) -> None:
    client = Playwright(bridge)
    target_id = await client.create_page()

    reply = await client.call("Target.closeTarget", {"targetId": target_id})

    assert reply.result == {"success": True}
    assert extension.closed_tab_ids() == [101]
    assert client.detached_targets() == [target_id]
    assert 101 not in bridge._tabs


@pytest.mark.asyncio
async def test_closing_a_tab_the_agent_did_not_open_only_lets_go_of_it(
    bridge: ExtensionCdpRelayBridge, extension: FakeExtension
) -> None:
    client = Playwright(bridge)
    bridge.sync_tabs([RelayTabInfo(tab_id=7, url="https://intranet.example/", title="Intranet", active=True)])
    attached = await bridge._ensure_tab_attached(7)
    bridge._announce_attached(client.client, 7, attached)
    extension.opens_no_tabs_of_its_own = True

    reply = await client.call("Target.closeTarget", {"targetId": attached.target_id})

    # Playwright only completes page.close() once the target detaches, so the user's tab is released, not left dangling.
    assert reply.result == {"success": True}
    assert client.detached_targets() == [attached.target_id]
    assert extension.detached_tab_ids() == [7]
    assert 7 not in bridge._tabs


@pytest.mark.asyncio
async def test_close_target_reports_a_failure_to_reach_the_extension_and_keeps_the_tab(
    bridge: ExtensionCdpRelayBridge, extension: FakeExtension
) -> None:
    client = Playwright(bridge)
    bridge.sync_tabs([RelayTabInfo(tab_id=7, url="https://intranet.example/", title="Intranet", active=True)])
    attached = await bridge._ensure_tab_attached(7)
    extension.close_fails_with = "Extension not connected"

    reply = await client.call("Target.closeTarget", {"targetId": attached.target_id})

    assert "Extension not connected" in str(reply.error["message"])
    assert 7 in bridge._tabs
    assert client.detached_targets() == []


@pytest.mark.asyncio
async def test_close_target_of_an_unknown_target_is_an_error(bridge: ExtensionCdpRelayBridge, extension: FakeExtension) -> None:
    client = Playwright(bridge)
    reply = await client.call("Target.closeTarget", {"targetId": "ghost"})
    assert reply.error["code"] == -32602
    assert extension.closed_tab_ids() == []
