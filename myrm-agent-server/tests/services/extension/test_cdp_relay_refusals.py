"""A tab that left the authorized sites is let go like a closed target, never answered command by command.

Playwright initialises a new page with a burst of commands and awaits them together. Answered one by one, the first
refusal rejects a command the driver has not started to await yet, and the unhandled rejection takes the driver down:
the Agent's whole browser connection with it. When the extension refuses a tab, the relay therefore ends the page's
session instead: Playwright fails every command in flight for the page at once, which it handles.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

import pytest

from app.services.extension.cdp_relay.manager import CdpRelayManager
from tests.support.cdp_relay_fakes import FakeExtension, RelayClient, WireExtension, settle

TAB = 101  # the first tab FakeExtension opens
INIT_BURST = ("Page.enable", "Browser.getWindowForTarget", "Page.getFrameTree")


@dataclass
class Relay:
    manager: CdpRelayManager
    client: RelayClient
    session_id: str
    extension: WireExtension

    def ask_all(self, methods: tuple[str, ...]) -> asyncio.Task[list[int]]:
        """Send the requests together; each is sent to the extension and waits there for its answer."""
        return asyncio.ensure_future(asyncio.gather(*(self.client.ask(self.session_id, method) for method in methods)))

    async def answer_the_release(self) -> None:
        """Answer the detach command the relay sends to release the tab, so nothing waits for it to time out."""
        for seq in self.extension.sequence_numbers("detach"):
            await self.manager.dispatch_extension_message({"type": "relay_result", "seq": seq, "result": {}})
        await settle(self.manager._bridge)


def _refusal(seq: int) -> dict[str, object]:
    return {"type": "relay_error", "seq": seq, "message": f"Tab {TAB} is not authorized", "code": "tab_not_authorized"}


@pytest.fixture
async def relay() -> Relay:
    manager = CdpRelayManager()
    manager._bridge.set_extension_transport(FakeExtension())
    client = RelayClient(manager._bridge)
    await client.create_page()
    return Relay(manager, client, client.session_of(f"target-{TAB}"), WireExtension(manager))


async def test_refused_commands_are_not_answered_one_by_one_and_the_page_is_let_go_once(relay: Relay) -> None:
    asked = relay.ask_all(INIT_BURST)
    await asyncio.sleep(0)

    for seq in relay.extension.sequence_numbers("cdp"):
        await relay.manager.dispatch_extension_message(_refusal(seq))
    request_ids = await asked
    await relay.answer_the_release()

    assert [relay.client.answers_to(request_id) for request_id in request_ids] == [[], [], []]
    assert relay.client.detached_targets() == [f"target-{TAB}"]
    assert len(relay.extension.sequence_numbers("detach")) == 1  # the debugger is released once, not once per command


async def test_a_command_that_failed_for_any_other_reason_is_answered_and_the_page_stays(relay: Relay) -> None:
    asked = relay.ask_all(("Page.reload",))
    await asyncio.sleep(0)

    (seq,) = relay.extension.sequence_numbers("cdp")
    await relay.manager.dispatch_extension_message({"type": "relay_error", "seq": seq, "message": "Debugger is not attached"})
    (request_id,) = await asked

    (answer,) = relay.client.answers_to(request_id)
    assert answer["error"] == {"message": "Debugger is not attached", "code": -32000}
    assert relay.client.detached_targets() == []
