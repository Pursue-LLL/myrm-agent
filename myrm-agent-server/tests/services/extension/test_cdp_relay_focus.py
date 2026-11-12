"""The CDP relay never lets a client take the user's focus.

Forwarded to Chrome, Page.bringToFront activates the tab and brings its window to the front. The Agent's
switch-tab sends it, so the relay acknowledges it without involving the browser; everything else a page
session sends still goes to the tab.
"""

from __future__ import annotations

import json

import pytest

from app.services.extension.cdp_relay.bridge import ExtensionCdpRelayBridge
from app.services.extension.cdp_relay.protocol import RelayTabInfo

TAB_ID = 7


class RecordingExtension:
    """Stands in for the MV3 extension and keeps every command the relay sends it."""

    def __init__(self) -> None:
        self.commands: list[dict[str, object]] = []

    async def __call__(self, command: dict[str, object]) -> object:
        self.commands.append(command)
        if command["type"] == "attach":
            return {"targetId": f"target-{command['tabId']}"}
        return {}

    def forwarded_methods(self) -> list[object]:
        return [command["method"] for command in self.commands if command["type"] == "cdp"]


class PageClient:
    """A CDP client attached to one tab, sending requests on that tab's page session."""

    def __init__(self, bridge: ExtensionCdpRelayBridge, session_id: str) -> None:
        self.bridge = bridge
        self.session_id = session_id
        self.replies: list[dict[str, object]] = []
        bridge.attach_cdp_client(lambda raw: self.replies.append(json.loads(raw)))
        self._next_id = 1

    async def send(self, method: str, session_id: str | None = None) -> dict[str, object]:
        request_id = self._next_id
        self._next_id += 1
        await self.bridge._handle_cdp_client_message(
            self.bridge._clients[-1],
            json.dumps({"id": request_id, "method": method, "params": {}, "sessionId": session_id or self.session_id}),
        )
        return next(reply for reply in reversed(self.replies) if reply.get("id") == request_id)


@pytest.fixture
def extension() -> RecordingExtension:
    return RecordingExtension()


@pytest.fixture
async def page(extension: RecordingExtension) -> PageClient:
    bridge = ExtensionCdpRelayBridge()
    bridge.set_extension_transport(extension)
    bridge.sync_tabs([RelayTabInfo(tab_id=TAB_ID, url="https://intranet.example/", title="Intranet", active=True)])
    attached = await bridge._ensure_tab_attached(TAB_ID)
    return PageClient(bridge, attached.session_id)


@pytest.mark.asyncio
async def test_bring_to_front_is_acknowledged_and_never_reaches_the_browser(
    page: PageClient, extension: RecordingExtension
) -> None:
    reply = await page.send("Page.bringToFront")

    assert reply == {"id": 1, "result": {}, "sessionId": page.session_id}
    assert extension.forwarded_methods() == []


@pytest.mark.asyncio
async def test_every_other_page_request_is_still_forwarded_to_the_tab(page: PageClient, extension: RecordingExtension) -> None:
    await page.send("Runtime.evaluate")
    await page.send("Page.bringToFront")
    await page.send("Page.captureScreenshot")

    assert extension.forwarded_methods() == ["Runtime.evaluate", "Page.captureScreenshot"]


@pytest.mark.asyncio
async def test_bring_to_front_on_an_unknown_session_is_still_an_error(page: PageClient, extension: RecordingExtension) -> None:
    reply = await page.send("Page.bringToFront", session_id="ghost")

    assert reply["error"] == {"message": "Session not found: ghost", "code": -32001}
    assert extension.forwarded_methods() == []
