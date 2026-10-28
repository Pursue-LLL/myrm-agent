"""A session runs one turn at a time, and a turn is ended by its own name.

The gate marks the next turn running in the very step that picks it, so a message that arrives between two turns of
a session waits behind the second one instead of starting a third. A turn is ended by naming it (``release_turn``): the
turn ending by itself and the stuck-task watchdog may both signal its end, and the one that comes second must not end
the turn that has taken over, even after the session record of the first was dropped and a new one created.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

import pytest

from app.channels.routing.session_gate import SessionGate, SessionGateConfig, gate_key
from app.channels.types import InboundMessage


def _dm(text: str) -> InboundMessage:
    return InboundMessage(channel="telegram", sender_id="u1", chat_id="u1", content=text)


class _Host:
    """What the router does with the gate: runs each turn it is handed and counts how many run at once."""

    def __init__(self, turn: Callable[[InboundMessage], Awaitable[None]], *, debounce_ms: int = 30) -> None:
        self.ran: list[str] = []
        self.running = 0
        self.most_running = 0
        self._turn = turn
        self.gate = SessionGate(SessionGateConfig(debounce_window_ms=debounce_ms, max_pending_per_session=10), on_ready=self._run)

    async def _run(self, msg: InboundMessage) -> None:
        self.ran.append(msg.content)
        self.running += 1
        self.most_running = max(self.most_running, self.running)
        try:
            await self._turn(msg)
        finally:
            self.running -= 1


async def _settle() -> None:
    await asyncio.sleep(0.3)


@pytest.mark.asyncio
async def test_a_message_between_two_turns_waits_behind_the_second() -> None:
    """The first turn ends with one message queued; a message arriving before that queued turn's task has run is not a third."""
    host: _Host

    async def turn(msg: InboundMessage) -> None:
        if msg.content == "first":
            await asyncio.sleep(0.1)
            # Runs ahead of the task the gate creates when this turn ends: the message lands in that very gap.
            asyncio.get_running_loop().call_soon(host.gate.submit, _dm("between"))
        else:
            await asyncio.sleep(0.1)

    host = _Host(turn)
    host.gate.submit(_dm("first"))
    await asyncio.sleep(0.06)
    host.gate.submit(_dm("queued"))
    await asyncio.sleep(0.8)

    assert host.ran == ["first", "queued", "between"]
    assert host.most_running == 1


@pytest.mark.asyncio
async def test_without_a_debounce_window_two_messages_of_one_tick_do_not_overlap() -> None:
    async def turn(msg: InboundMessage) -> None:
        await asyncio.sleep(0.05)

    host = _Host(turn, debounce_ms=0)
    host.gate.submit(_dm("a"))
    host.gate.submit(_dm("b"))
    await _settle()

    assert host.ran == ["a", "b"]
    assert host.most_running == 1


@pytest.mark.asyncio
async def test_releasing_a_stuck_turn_starts_the_one_queued_behind_it() -> None:
    stuck = asyncio.Event()

    async def turn(msg: InboundMessage) -> None:
        if msg.content == "stuck":
            await stuck.wait()

    host = _Host(turn)
    host.gate.submit(_dm("stuck"))
    await asyncio.sleep(0.06)
    host.gate.submit(_dm("waiting"))
    key = gate_key(_dm("x"))

    host.gate.release_turn(key, host.gate.running_turn(key))
    await _settle()

    assert host.ran == ["stuck", "waiting"]
    stuck.set()


@pytest.mark.asyncio
async def test_the_late_end_of_a_released_turn_does_not_end_the_turn_that_took_over() -> None:
    """The watchdog released the stuck turn; when that turn finally unwinds, the new turn keeps its place."""
    first_task: list[asyncio.Task[None] | None] = []
    stuck = asyncio.Event()
    finish = asyncio.Event()

    async def turn(msg: InboundMessage) -> None:
        if msg.content == "stuck":
            first_task.append(asyncio.current_task())
            await stuck.wait()
        elif msg.content == "waiting":
            await finish.wait()

    host = _Host(turn)
    host.gate.submit(_dm("stuck"))
    await asyncio.sleep(0.06)
    host.gate.submit(_dm("waiting"))
    key = gate_key(_dm("x"))
    host.gate.release_turn(key, host.gate.running_turn(key))
    await asyncio.sleep(0.05)

    task = first_task[0]
    assert task is not None
    task.cancel()
    await asyncio.sleep(0.05)
    host.gate.submit(_dm("later"))
    await asyncio.sleep(0.2)

    assert host.ran == ["stuck", "waiting"]
    assert host.most_running == 2  # the stuck turn is still counted until it unwinds; "later" never joined them
    finish.set()
    await _settle()
    assert host.ran == ["stuck", "waiting", "later"]


@pytest.mark.asyncio
async def test_a_released_turn_whose_session_record_is_gone_cannot_end_a_later_turn() -> None:
    """Turn numbers are never reused: the stuck turn's late end finds a record of another turn, not its own."""
    first_task: list[asyncio.Task[None] | None] = []
    stuck = asyncio.Event()
    finish = asyncio.Event()

    async def turn(msg: InboundMessage) -> None:
        if msg.content == "stuck":
            first_task.append(asyncio.current_task())
            await stuck.wait()
        elif msg.content == "next":
            await finish.wait()

    host = _Host(turn)
    host.gate.submit(_dm("stuck"))
    await asyncio.sleep(0.06)
    key = gate_key(_dm("x"))
    host.gate.release_turn(key, host.gate.running_turn(key))  # nothing waits: the session record is dropped
    host.gate.submit(_dm("next"))
    await asyncio.sleep(0.1)

    task = first_task[0]
    assert task is not None
    task.cancel()
    await asyncio.sleep(0.05)
    host.gate.submit(_dm("after"))
    await asyncio.sleep(0.2)

    assert host.ran == ["stuck", "next"]
    finish.set()
    await _settle()
    assert host.ran == ["stuck", "next", "after"]


@pytest.mark.asyncio
async def test_a_turn_that_ended_cannot_be_released_again() -> None:
    hold_second = asyncio.Event()

    async def turn(msg: InboundMessage) -> None:
        if msg.content == "b":
            await hold_second.wait()
        else:
            await asyncio.sleep(0.05)

    host = _Host(turn)
    key = gate_key(_dm("x"))
    host.gate.submit(_dm("a"))
    await asyncio.sleep(0.06)
    ended = host.gate.running_turn(key)
    assert ended > 0
    host.gate.submit(_dm("b"))
    await asyncio.sleep(0.12)  # a ended, b is running
    running = host.gate.running_turn(key)
    assert running > ended

    host.gate.release_turn(key, ended)

    assert host.gate.running_turn(key) == running
    hold_second.set()


@pytest.mark.asyncio
async def test_an_idle_session_has_no_running_turn() -> None:
    async def turn(msg: InboundMessage) -> None:
        return None

    host = _Host(turn)
    assert host.gate.running_turn(gate_key(_dm("x"))) == 0
    host.gate.submit(_dm("a"))
    await _settle()
    assert host.gate.running_turn(gate_key(_dm("x"))) == 0


@pytest.mark.asyncio
async def test_a_turn_that_fails_still_starts_the_one_queued_behind_it() -> None:
    async def turn(msg: InboundMessage) -> None:
        if msg.content == "boom":
            await asyncio.sleep(0.05)
            raise RuntimeError("boom")

    host = _Host(turn)
    host.gate.submit(_dm("boom"))
    await asyncio.sleep(0.06)
    host.gate.submit(_dm("after"))
    await _settle()

    assert host.ran == ["boom", "after"]
    assert host.most_running == 1


@pytest.mark.asyncio
async def test_a_cancelled_turn_still_starts_the_one_queued_behind_it() -> None:
    stuck = asyncio.Event()
    running: list[asyncio.Task[None] | None] = []

    async def turn(msg: InboundMessage) -> None:
        if msg.content == "stuck":
            running.append(asyncio.current_task())
            await stuck.wait()

    host = _Host(turn)
    host.gate.submit(_dm("stuck"))
    await asyncio.sleep(0.06)
    host.gate.submit(_dm("after"))
    task = running[0]
    assert task is not None
    task.cancel()
    await _settle()

    assert host.ran == ["stuck", "after"]
