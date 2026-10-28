"""``/steer`` is how text reaches a run that is already going: who may use it, and when there is nothing to steer.

A group run executes as the person whose message started it, so only that person steers it; a finished turn that stays
registered only to keep its approval answerable has no run left. Runs on the real ``AgentRouter`` dispatch, with a run
registered by hand and the session gate recording what is submitted to it.
"""

from __future__ import annotations

import asyncio
import dataclasses
from unittest.mock import MagicMock

import pytest
from myrm_agent_harness.utils.runtime.cancellation import CancellationToken
from myrm_agent_harness.utils.runtime.steering import SteeringToken

from app.channels.i18n import get_text
from app.channels.routing.router import AgentRouter
from app.channels.routing.router_keys import routing_state_key
from app.channels.routing.router_models import _ActiveTask
from app.channels.types import InboundMessage

from .risk_gate_testkit import make_bus, make_router

_CHAT = "chat-1"
_INSTRUCTION = "only keep the 2026 rows"


def _steer(sender: str = "alice", *, is_group: bool = True) -> InboundMessage:
    return InboundMessage(
        channel="telegram",
        sender_id=sender,
        chat_id=_CHAT,
        is_group=is_group,
        content=f"/steer {_INSTRUCTION}",
        message_id="m1",
        metadata={"locale": "en"},
    )


@dataclasses.dataclass
class _Chat:
    """A chat with one registered run: the router, the run's steering token, and what the router handed out."""

    router: AgentRouter
    token: SteeringToken
    bus: MagicMock
    submit: MagicMock

    async def say(self, msg: InboundMessage) -> list[str]:
        """Dispatch ``msg`` and return the texts the router published in answer."""
        await self.router._dispatch_inbound_message(msg)
        await asyncio.sleep(0)
        return [call.args[0].content for call in self.bus.publish_outbound.await_args_list]


async def _chat_with_run(*, requester_id: str, finished: bool = False) -> _Chat:
    bus = make_bus()
    router = make_router(bus)
    submit = MagicMock()
    router._gate.submit = submit  # type: ignore[method-assign]
    token = SteeringToken()
    task = asyncio.current_task()
    if finished:
        task = asyncio.create_task(asyncio.sleep(0))
        await task
    assert task is not None
    router._active_tasks[routing_state_key("telegram", _CHAT, None)] = _ActiveTask(
        task=task,
        cancel_token=CancellationToken(),
        channel="telegram",
        chat_id=_CHAT,
        placeholder_id=None,
        started_at=0.0,
        requester_id=requester_id,
        steering_token=token,
    )
    return _Chat(router, token, bus, submit)


async def test_the_person_whose_message_started_a_group_run_steers_it() -> None:
    chat = await _chat_with_run(requester_id="alice")

    replies = await chat.say(_steer("alice"))

    assert chat.token.activate() == [_INSTRUCTION]
    assert replies == [get_text(_steer(), "steering_applied", preview=_INSTRUCTION)]
    chat.submit.assert_not_called()


async def test_another_member_of_the_group_cannot_steer_the_run() -> None:
    chat = await _chat_with_run(requester_id="alice")

    replies = await chat.say(_steer("bob"))

    assert not chat.token.has_pending
    assert replies == [get_text(_steer("bob"), "steer_requester_only")]
    chat.submit.assert_not_called()


async def test_a_group_run_with_no_known_requester_is_steered_by_nobody() -> None:
    chat = await _chat_with_run(requester_id="")

    replies = await chat.say(_steer("alice"))

    assert not chat.token.has_pending
    assert replies == [get_text(_steer(), "steer_requester_only")]


async def test_a_direct_chat_has_one_person_so_the_run_is_steered_without_asking_who_started_it() -> None:
    chat = await _chat_with_run(requester_id="")

    await chat.say(_steer("alice", is_group=False))

    assert chat.token.activate() == [_INSTRUCTION]


@pytest.mark.parametrize("is_group", [True, False])
async def test_a_finished_turn_has_nothing_to_steer_so_the_instruction_is_a_turn_of_its_own(is_group: bool) -> None:
    """The turn stays registered only so its approval can be answered; steering it would acknowledge and drop the text."""
    chat = await _chat_with_run(requester_id="alice", finished=True)

    replies = await chat.say(_steer("alice", is_group=is_group))

    assert not chat.token.has_pending
    assert replies == []
    chat.submit.assert_called_once()
    assert chat.submit.call_args.args[0].content == _INSTRUCTION


@pytest.mark.parametrize("locale", ["en", "zh-CN", "ja"])
def test_the_queued_acknowledgement_tells_who_started_the_run_how_to_redirect_it(locale: str) -> None:
    msg = InboundMessage(channel="telegram", sender_id="bob", content="x", metadata={"locale": locale})

    text = get_text(msg, "busy_ack_queued", position=2, max_pending=10)

    assert "/steer" in text
    assert "2" in text and "10" in text


@pytest.mark.parametrize("locale", ["en", "zh-CN", "zh-TW", "ja"])
def test_the_refusal_for_a_member_who_did_not_start_the_run_is_localized(locale: str) -> None:
    msg = InboundMessage(channel="telegram", sender_id="bob", content="x", metadata={"locale": locale})

    assert get_text(msg, "steer_requester_only") != "steer_requester_only"
