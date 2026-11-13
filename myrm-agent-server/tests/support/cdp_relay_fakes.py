"""A stand-in extension and a CDP client for driving the extension CDP relay without a browser.

[INPUT]
- app.services.extension.cdp_relay.bridge::ExtensionCdpRelayBridge (POS: the relay a client talks to)

[OUTPUT]
- FakeExtension: answers the relay's commands the way the MV3 extension does and records them
- WireExtension: the extension as the WebSocket shows it, answering only when the test says so
- RelayClient: a CDP client of the relay, keeping every frame the relay answers or announces
- Reply: one answer, as its result or error object
- AUTO_ATTACH, auto_attaching_client, settle: a client connected the way Playwright connects, and a wait for the work the
  relay starts on its own

[POS]
Server pytest-only helpers shared by the relay's unit tests: each drives the relay through the interface Playwright
uses and watches what the extension is asked to do, instead of keeping a private copy of these fakes.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass

from app.services.extension.cdp_relay.bridge import ExtensionCdpRelayBridge
from app.services.extension.cdp_relay.manager import CdpRelayManager

AUTO_ATTACH = {"autoAttach": True, "waitForDebuggerOnStart": True, "flatten": True}


class FakeExtension:
    """Stands in for the MV3 extension: records every relay command and answers the way the real one does."""

    def __init__(self) -> None:
        self.commands: list[dict[str, object]] = []
        self.opens_no_tabs_of_its_own = False
        self.close_fails_with: str | None = None
        self.attach_fails_with: str | None = None
        self._next_tab_id = 100

    async def __call__(self, command: dict[str, object]) -> object:
        self.commands.append(command)
        kind = command["type"]
        if kind == "createTab":
            self._next_tab_id += 1
            return {"tabId": self._next_tab_id}
        if kind == "attach":
            if self.attach_fails_with is not None:
                raise RuntimeError(self.attach_fails_with)
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

    def attached_tab_ids(self) -> list[object]:
        return [command["tabId"] for command in self.commands if command["type"] == "attach"]

    def detached_tab_ids(self) -> list[object]:
        return [command["tabId"] for command in self.commands if command["type"] == "detach"]


class WireExtension:
    """The extension as the WebSocket shows it: relay commands go out with a sequence number, answers come back later."""

    def __init__(self, manager: CdpRelayManager) -> None:
        self.sent: list[dict[str, object]] = []
        manager._bridge.set_extension_transport(manager._bridge.make_extension_caller(self._send))

    async def _send(self, message: dict[str, object]) -> None:
        self.sent.append(message)

    def sequence_numbers(self, command_type: str | None = None) -> list[int]:
        """Sequence numbers of the commands sent so far, of one type when given."""
        numbers: list[int] = []
        for message in self.sent:
            command = message["command"]
            assert isinstance(command, dict) and isinstance(message["seq"], int), message
            if command_type is None or command["type"] == command_type:
                numbers.append(message["seq"])
        return numbers


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


class RelayClient:
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

    async def ask(self, session_id: str, method: str) -> int:
        """Send a request on a page's session and return its id once the relay has dealt with it; it may never answer."""
        request_id = self._next_id
        self._next_id += 1
        await self.bridge._handle_cdp_client_message(
            self.client, json.dumps({"id": request_id, "method": method, "params": {}, "sessionId": session_id})
        )
        return request_id

    def answers_to(self, request_id: int) -> list[dict[str, object]]:
        return [frame for frame in self.frames if frame.get("id") == request_id]

    def session_of(self, target_id: str) -> str:
        """The session the relay announced the target on."""
        for frame in self.frames:
            params = frame.get("params")
            if frame.get("method") == "Target.attachedToTarget" and isinstance(params, dict):
                info = params["targetInfo"]
                if isinstance(info, dict) and info["targetId"] == target_id:
                    return str(params["sessionId"])
        raise AssertionError(f"{target_id} was never announced to this client")

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

    def announced(self) -> dict[str, dict[str, object]]:
        """Target id → targetInfo, as carried by every Target.attachedToTarget the client received."""
        announced: dict[str, dict[str, object]] = {}
        for frame in self.frames:
            if frame.get("method") == "Target.attachedToTarget":
                params = frame["params"]
                assert isinstance(params, dict)
                info = params["targetInfo"]
                assert isinstance(info, dict)
                announced[str(info["targetId"])] = info
        return announced

    def announced_contexts(self) -> dict[str, object]:
        """Target id → browserContextId, as carried by every Target.attachedToTarget the client received."""
        return {target_id: info["browserContextId"] for target_id, info in self.announced().items()}

    def detached_targets(self) -> list[object]:
        targets: list[object] = []
        for frame in self.frames:
            if frame.get("method") == "Target.detachedFromTarget":
                params = frame["params"]
                assert isinstance(params, dict)
                targets.append(params["targetId"])
        return targets


async def settle(bridge: ExtensionCdpRelayBridge) -> None:
    """Wait for the work the relay started on its own."""
    await asyncio.gather(*bridge._background_tasks)


async def auto_attaching_client(bridge: ExtensionCdpRelayBridge, context_id: str | None = None) -> RelayClient:
    """A client the way Playwright connects: auto-attach on, one page of its own open."""
    client = RelayClient(bridge)
    await client.call("Target.setAutoAttach", AUTO_ATTACH)
    await client.create_page(context_id)
    return client
