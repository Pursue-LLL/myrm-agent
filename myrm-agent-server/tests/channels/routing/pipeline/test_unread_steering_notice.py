"""A chat turn that ends by itself without reading a ``/steer`` instruction it accepted gives it back to the sender.

Runs the real ``AgentRouter._execute_prepared_context`` and the real task registry around a scripted agent stream: the
script accepts instructions the way ``/steer`` does, then ends the way the case under test ends (an error, a ``/stop``,
a run that read what it was given). The model never reads in these scripts, so what stays in the token is exactly what
the turn owner has to deal with. A ``/stop`` ends the run and the guidance addressed to it, so it sends no notice.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Callable
from unittest.mock import AsyncMock, MagicMock

import pytest
from myrm_agent_harness.utils.runtime.steering import SteeringToken

from app.channels.i18n import get_text
from app.channels.routing.router import AgentRouter
from app.channels.routing.router_models import _AgentTurnScratch, _RouterExecutionContext
from app.channels.types import InboundMessage, OutboundMessage

_CHAT = "chat-9"
_STATE_KEY = "telegram:chat-9"
_FIRST = "only keep the 2026 rows"
_SECOND = "and cite the source"

Script = Callable[[SteeringToken], AsyncGenerator[object, None]]


def _msg(*, is_group: bool = False) -> InboundMessage:
    return InboundMessage(
        channel="telegram",
        sender_id="u1",
        chat_id=_CHAT,
        is_group=is_group,
        content="write the Q3 report",
        message_id="m1",
        metadata={"locale": "en"},
    )


class _Chat:
    """A real router whose agent stream is ``script``; ``execute`` runs the router's real execute step on one message."""

    def __init__(self, script: Script) -> None:
        self.token: SteeringToken | None = None
        self.accepted = asyncio.Event()
        self._script = script
        self.bus = MagicMock()
        self.bus.consume_inbound = AsyncMock(side_effect=TimeoutError)
        self.bus.publish_outbound = AsyncMock()
        self.bus.get_channel = MagicMock(return_value=None)
        executor = MagicMock()
        executor.execute_stream = self._stream
        self.router = AgentRouter(bus=self.bus, pairing_store=MagicMock(), agent_executor=executor)
        self.router._resolve_mobile_status_deep_link = AsyncMock(return_value=None)  # type: ignore[method-assign]

    async def _stream(self, *_args: object, steering_token: SteeringToken, **_kwargs: object) -> AsyncGenerator[object, None]:
        self.token = steering_token
        async for event in self._script(steering_token):
            yield event
        self.accepted.set()

    async def execute(self, msg: InboundMessage) -> None:
        ctx = _RouterExecutionContext(
            user_id="u1", state_key=_STATE_KEY, chat_id=_CHAT, message_id="m1", topic_ctx=None, exec_msg=msg
        )
        await self.router._execute_prepared_context(ctx, _AgentTurnScratch(), is_resume=False, inbound_had_voice=False)

    def sent(self) -> list[OutboundMessage]:
        return [call.args[0] for call in self.bus.publish_outbound.await_args_list]


def _accepts(*instructions: str) -> Script:
    """A run that accepts the instructions and then ends, having read none of them."""

    async def script(token: SteeringToken) -> AsyncGenerator[object, None]:
        for instruction in instructions:
            assert token.steer(instruction) is True
        return
        yield

    return script


async def test_a_run_that_fails_hands_back_the_instruction_it_never_read() -> None:
    async def fails(token: SteeringToken) -> AsyncGenerator[object, None]:
        assert token.steer(_FIRST) is True
        raise RuntimeError("provider exploded")
        yield

    chat = _Chat(fails)

    with pytest.raises(RuntimeError, match="provider exploded"):
        await chat.execute(_msg())

    [notice] = chat.sent()
    assert notice.content == get_text(_msg(), "steering_unread", instructions=f"- {_FIRST}")
    assert notice.recipient_id == "u1"
    assert _FIRST in notice.content


async def test_a_run_the_user_stopped_ends_with_its_unread_instruction_and_sends_no_notice() -> None:
    async def waits(token: SteeringToken) -> AsyncGenerator[object, None]:
        assert token.steer(_FIRST) is True
        await asyncio.sleep(3600)
        yield

    chat = _Chat(waits)
    turn = asyncio.create_task(chat.execute(_msg()))
    while chat.token is None:
        await asyncio.sleep(0)

    assert await chat.router._abort_session_task(_STATE_KEY, "User /stop command") is True
    await turn

    assert chat.sent() == []
    assert chat.token.steer(_SECOND) is False


async def test_every_unread_instruction_comes_back_in_one_notice_in_the_order_it_was_sent() -> None:
    chat = _Chat(_accepts(_FIRST, _SECOND))

    await chat.execute(_msg())

    [notice] = chat.sent()
    assert notice.content == get_text(_msg(), "steering_unread", instructions=f"- {_FIRST}\n- {_SECOND}")


async def test_a_run_that_read_what_it_accepted_hands_back_nothing() -> None:
    async def reads(token: SteeringToken) -> AsyncGenerator[object, None]:
        assert token.steer(_FIRST) is True
        assert token.collect_all_steering_messages() == [_FIRST]
        return
        yield

    chat = _Chat(reads)

    await chat.execute(_msg())

    assert chat.sent() == []


async def test_an_instruction_sent_after_the_turn_ended_is_refused_so_it_becomes_a_turn_of_its_own() -> None:
    chat = _Chat(_accepts())

    await chat.execute(_msg())

    assert chat.token is not None
    assert chat.token.steer(_FIRST) is False


async def test_the_notice_in_a_group_goes_to_the_chat_quoting_the_message_that_started_the_run() -> None:
    chat = _Chat(_accepts(_FIRST))

    await chat.execute(_msg(is_group=True))

    [notice] = chat.sent()
    assert (notice.recipient_id, notice.reply_to_id) == (_CHAT, "m1")


async def test_a_notice_that_cannot_be_sent_does_not_fail_the_turn_or_leave_the_run_registered() -> None:
    chat = _Chat(_accepts(_FIRST))
    chat.bus.publish_outbound = AsyncMock(side_effect=RuntimeError("channel down"))

    await chat.execute(_msg())

    assert _STATE_KEY not in chat.router._active_tasks
