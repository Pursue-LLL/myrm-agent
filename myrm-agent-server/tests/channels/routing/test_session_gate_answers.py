"""An answer to a run suspended at a tool approval reaches the router as sent, and before the text beside it.

The gate hands the router one turn at a time. Text is merged into one turn, which builds a plain message, so an answer
merged with text would lose its ``resume_value``; and any text turn of the session ends the run the answer belongs to,
so text must not run before an answer that is waiting. The host here calls ``on_task_complete`` the way the router does
when a turn ends.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from unittest.mock import AsyncMock

import pytest

from app.channels.routing.session_gate import SessionGate, SessionGateConfig
from app.channels.types import InboundMessage

_ANSWER: dict[str, object] = {"decisions": [{"type": "approve"}]}


def _text(content: str) -> InboundMessage:
    return InboundMessage(channel="telegram", sender_id="u1", chat_id="c1", content=content)


def _answer(label: str = "answer") -> InboundMessage:
    return InboundMessage(
        channel="telegram", sender_id="u1", chat_id="c1", content="", resume_value=_ANSWER, metadata={"label": label}
    )


class _Router:
    """What the router does with the gate: runs each turn it is handed and signals its end."""

    def __init__(self, turn: Callable[[InboundMessage], Awaitable[None]] | None = None) -> None:
        self.turns: list[InboundMessage] = []
        self.running = 0
        self.most_running = 0
        self.gate = SessionGate(SessionGateConfig(debounce_window_ms=30, max_pending_per_session=2), on_ready=self._run)
        self._turn = turn

    async def _run(self, msg: InboundMessage) -> None:
        self.turns.append(msg)
        self.running += 1
        self.most_running = max(self.most_running, self.running)
        try:
            if self._turn is not None:
                await self._turn(msg)
        finally:
            self.running -= 1
            self.gate.on_task_complete(msg)

    def kinds(self) -> list[str]:
        """What ran, in order: the label of an answer, or the merged text of a text turn."""
        return [str(t.metadata["label"]) if t.resume_value is not None else t.content for t in self.turns]


async def _settle() -> None:
    await asyncio.sleep(0.25)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("arrivals", "ran"),
    [
        ([_text("and also check X"), _answer()], ["answer", "and also check X"]),
        ([_answer(), _text("and also check X")], ["answer", "and also check X"]),
        ([_text("a"), _text("b"), _answer(), _text("c")], ["answer", "a\nb\nc"]),
    ],
)
async def test_an_answer_within_the_debounce_window_of_text_runs_first_and_intact(
    arrivals: list[InboundMessage], ran: list[str]
) -> None:
    router = _Router()

    for msg in arrivals:
        router.gate.submit(msg)
    await _settle()

    assert router.kinds() == ran
    assert router.turns[0].resume_value == _ANSWER


@pytest.mark.asyncio
async def test_several_answers_each_run_alone_in_the_order_they_came() -> None:
    router = _Router()

    router.gate.submit(_answer("first"))
    router.gate.submit(_text("between"))
    router.gate.submit(_answer("second"))
    await _settle()

    assert router.kinds() == ["first", "second", "between"]


@pytest.mark.asyncio
async def test_an_answer_that_arrives_during_a_turn_runs_before_the_text_queued_in_that_turn() -> None:
    proceed = asyncio.Event()

    async def first_turn_waits(msg: InboundMessage) -> None:
        if msg.content == "first":
            await proceed.wait()

    router = _Router(first_turn_waits)
    router.gate.submit(_text("first"))
    await _settle()

    router.gate.submit(_text("queued text"))
    router.gate.submit(_answer())
    await asyncio.sleep(0.05)
    assert router.kinds() == ["first"]

    proceed.set()
    await _settle()

    assert router.kinds() == ["first", "answer", "queued text"]


@pytest.mark.asyncio
async def test_an_answer_is_kept_when_the_queue_of_waiting_text_is_full() -> None:
    proceed = asyncio.Event()

    async def first_turn_waits(msg: InboundMessage) -> None:
        if msg.content == "first":
            await proceed.wait()

    router = _Router(first_turn_waits)
    router.gate.submit(_text("first"))
    await _settle()

    router.gate.submit(_text("p1"))
    router.gate.submit(_text("p2"))
    router.gate.submit(_text("dropped: the queue holds two"))
    router.gate.submit(_answer())
    proceed.set()
    await _settle()

    assert router.kinds() == ["first", "answer", "p1\np2"]


@pytest.mark.asyncio
async def test_an_answer_is_not_announced_as_a_message_waiting_behind_a_busy_turn() -> None:
    proceed = asyncio.Event()

    async def first_turn_waits(msg: InboundMessage) -> None:
        if msg.content == "first":
            await proceed.wait()

    on_busy_ack = AsyncMock()
    router = _Router(first_turn_waits)
    router.gate = SessionGate(SessionGateConfig(debounce_window_ms=30), on_ready=router._run, on_busy_ack=on_busy_ack)
    router.gate.submit(_text("first"))
    await _settle()

    router.gate.submit(_answer())
    await asyncio.sleep(0.05)
    proceed.set()
    await _settle()

    on_busy_ack.assert_not_awaited()
    assert router.kinds() == ["first", "answer"]


@pytest.mark.asyncio
async def test_turns_never_overlap_when_answers_and_text_wait_together() -> None:
    async def takes_a_while(_msg: InboundMessage) -> None:
        await asyncio.sleep(0.05)

    router = _Router(takes_a_while)
    for msg in (_text("a"), _answer("one"), _text("b"), _answer("two"), _text("c")):
        router.gate.submit(msg)
    await asyncio.sleep(0.8)

    assert router.kinds() == ["one", "two", "a\nb\nc"]
    assert router.most_running == 1


@pytest.mark.asyncio
async def test_text_alone_is_merged_and_queued_as_before() -> None:
    router = _Router()

    router.gate.submit(_text("one"))
    router.gate.submit(_text("two"))
    await _settle()

    assert router.kinds() == ["one\ntwo"]
