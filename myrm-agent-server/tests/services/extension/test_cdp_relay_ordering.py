"""What the extension sends reaches a CDP client in the order the extension sent it.

Playwright registers its lifecycle listener in the reply to ``Page.getFrameTree`` and relies on the events Chrome
replays right after that reply. A page the Agent attaches to after it has loaded gets its ``load`` event only if the
reply comes first: when the events overtake it, ``wait_for_load_state()`` waits forever for an event that was dropped.
The extension's WebSocket hands the relay a reply and the events behind it in one burst, so the relay itself must not
let them change places.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass

import pytest

from app.services.extension.cdp_relay.manager import CdpRelayManager
from tests.support.cdp_relay_fakes import FakeExtension, RelayClient, WireExtension

TAB = 101  # the first tab FakeExtension opens


@dataclass
class Relay:
    """A client with one attached page whose commands go over the wire to ``WireExtension``."""

    manager: CdpRelayManager
    client: RelayClient
    session_id: str
    extension: WireExtension
    frames_before: int

    def ask(self, request_id: int, method: str) -> asyncio.Task[None]:
        request = {"id": request_id, "method": method, "sessionId": self.session_id}
        return asyncio.create_task(self.client.bridge._handle_cdp_client_message(self.client.client, json.dumps(request)))

    async def receive_together(self, messages: list[dict[str, object]]) -> None:
        """Handle messages one after the other without a loop turn in between, as the receive loop does for a burst."""
        for message in messages:
            await self.manager.dispatch_extension_message(message)

    def seen(self) -> list[object]:
        """Replies by request id and lifecycle events by name, in the order the client received them."""
        seen: list[object] = []
        for frame in self.client.frames[self.frames_before :]:
            if "id" in frame:
                seen.append(frame["id"])
            elif frame.get("method") == "Page.lifecycleEvent":
                params = frame["params"]
                assert isinstance(params, dict)
                seen.append(params["name"])
        return seen


def _result(seq: int) -> dict[str, object]:
    return {"type": "relay_result", "seq": seq, "result": {}}


def _failure(seq: int) -> dict[str, object]:
    return {"type": "relay_error", "seq": seq, "message": "Debugger is not attached"}


def _lifecycle(name: str) -> dict[str, object]:
    return {"type": "cdp_event", "tabId": TAB, "method": "Page.lifecycleEvent", "params": {"name": name}}


@pytest.fixture
async def relay() -> Relay:
    manager = CdpRelayManager()
    manager._bridge.set_extension_transport(FakeExtension())
    client = RelayClient(manager._bridge)
    await client.create_page()
    return Relay(manager, client, client.session_of(f"target-{TAB}"), WireExtension(manager), frames_before=len(client.frames))


async def test_a_reply_reaches_the_client_before_the_events_the_extension_sent_after_it(relay: Relay) -> None:
    asked = relay.ask(50, "Page.getFrameTree")
    await asyncio.sleep(0)

    await relay.receive_together(
        [_result(relay.extension.sequence_numbers()[0]), _lifecycle("DOMContentLoaded"), _lifecycle("load")]
    )
    await asked

    assert relay.seen() == [50, "DOMContentLoaded", "load"]


async def test_a_failure_reaches_the_client_before_the_events_the_extension_sent_after_it(relay: Relay) -> None:
    asked = relay.ask(50, "Page.reload")
    await asyncio.sleep(0)

    await relay.receive_together([_failure(relay.extension.sequence_numbers()[0]), _lifecycle("init")])
    await asked

    assert relay.seen() == [50, "init"]


async def test_replies_and_events_that_arrive_together_keep_the_order_they_were_sent_in(relay: Relay) -> None:
    asked = [relay.ask(request_id, "Page.enable") for request_id in (50, 51, 52)]
    await asyncio.sleep(0)
    first, second, third = relay.extension.sequence_numbers()

    await relay.receive_together(
        [_result(first), _lifecycle("init"), _result(second), _lifecycle("DOMContentLoaded"), _result(third), _lifecycle("load")]
    )
    await asyncio.gather(*asked)

    assert relay.seen() == [50, "init", 51, "DOMContentLoaded", 52, "load"]
