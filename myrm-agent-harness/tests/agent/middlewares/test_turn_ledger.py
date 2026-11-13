"""TurnLedger: the calls of one model message still on their way to the conflict gate, in the model's order."""

from __future__ import annotations

import asyncio

import pytest
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage

from myrm_agent_harness.agent.middlewares.concurrency.turn_ledger import KEPT_TURNS, CallTurn, NoTurn, TurnLedger

SAFE = "file_read_tool"
UNSAFE = "file_write_tool"


def _message(call_ids: dict[str, str], message_id: str | None = "turn-1") -> AIMessage:
    """The model message that made *call_ids* (call id to tool name)."""
    return AIMessage(
        content="",
        id=message_id,
        tool_calls=[{"id": call_id, "name": name, "args": {}} for call_id, name in call_ids.items()],
    )


def _state(*messages: BaseMessage) -> dict[str, list[BaseMessage]]:
    return {"messages": [HumanMessage(content="go"), *messages]}


def _turn(ledger: TurnLedger, state: object, call_id: str) -> CallTurn:
    turn = ledger.turn_of(state, call_id)
    assert isinstance(turn, CallTurn)
    return turn


async def test_every_call_of_a_message_gets_the_same_turn() -> None:
    ledger = TurnLedger()
    state = _state(_message({"a": UNSAFE, "b": UNSAFE, "c": SAFE}))

    turns = [ledger.turn_of(state, call_id) for call_id in ("c", "a", "b")]

    assert isinstance(turns[0], CallTurn)
    assert turns[1] is turns[2] is turns[0]


async def test_a_call_is_to_wait_for_the_conflicting_calls_ahead_of_it_that_have_not_arrived() -> None:
    ledger = TurnLedger()
    turn = _turn(ledger, _state(_message({"a": UNSAFE, "b": SAFE, "c": UNSAFE, "d": SAFE})), "a")

    assert turn.unarrived_ahead_of("a", exclusive=True) == []
    assert turn.unarrived_ahead_of("b", exclusive=False) == ["a"]
    assert turn.unarrived_ahead_of("c", exclusive=True) == ["a", "b"]
    assert turn.unarrived_ahead_of("d", exclusive=False) == ["a", "c"]

    turn.mark_arrived("a")

    assert turn.unarrived_ahead_of("d", exclusive=False) == ["c"]


async def test_concurrency_safe_calls_are_never_waited_for_by_each_other() -> None:
    ledger = TurnLedger()
    turn = _turn(ledger, _state(_message({"a": SAFE, "b": SAFE, "c": SAFE})), "a")

    assert turn.unarrived_ahead_of("c", exclusive=False) == []


async def test_a_tool_nobody_declared_is_ordered_like_a_mutating_one() -> None:
    ledger = TurnLedger()
    turn = _turn(ledger, _state(_message({"a": "mcp__weather__lookup", "b": SAFE})), "a")

    assert turn.unarrived_ahead_of("b", exclusive=False) == ["a"]


async def test_calls_that_already_have_an_answer_are_not_part_of_the_turn() -> None:
    ledger = TurnLedger()
    state = _state(_message({"a": UNSAFE, "b": UNSAFE, "c": UNSAFE}), ToolMessage(content="done", tool_call_id="a"))

    turn = _turn(ledger, state, "c")

    assert "a" not in turn
    assert turn.unarrived_ahead_of("c", exclusive=True) == ["b"]


async def test_the_turn_belongs_to_the_message_that_made_the_call_not_to_the_latest_one() -> None:
    ledger = TurnLedger()
    state = _state(
        _message({"old-a": UNSAFE, "old-b": UNSAFE}, message_id="old"),
        ToolMessage(content="done", tool_call_id="old-a"),
        _message({"new-a": UNSAFE, "new-b": UNSAFE}, message_id="new"),
    )

    turn = _turn(ledger, state, "old-b")

    assert "old-b" in turn
    assert "new-a" not in turn


async def test_a_call_whose_message_made_no_other_call_has_no_turn() -> None:
    ledger = TurnLedger()

    assert ledger.turn_of(_state(_message({"a": UNSAFE})), "a") is NoTurn.LONE_CALL


@pytest.mark.parametrize(
    "state",
    [
        pytest.param(_state(_message({"a": UNSAFE, "b": UNSAFE}, message_id=None)), id="message-without-id"),
        pytest.param(_state(_message({"b": UNSAFE, "": UNSAFE})), id="blank-call-id-in-the-message"),
        pytest.param(_state(HumanMessage(content="no model message")), id="no-model-message"),
        pytest.param({"messages": None}, id="no-messages"),
        pytest.param({}, id="empty-state"),
        pytest.param(object(), id="state-is-not-a-mapping"),
    ],
)
async def test_a_call_that_cannot_be_placed_in_its_message_is_unidentified(state: object) -> None:
    assert TurnLedger().turn_of(state, "b") is NoTurn.UNIDENTIFIED


async def test_a_message_that_repeats_a_call_id_is_unidentified() -> None:
    message = AIMessage(
        content="",
        id="turn-1",
        tool_calls=[{"id": "a", "name": UNSAFE, "args": {}}, {"id": "a", "name": SAFE, "args": {}}],
    )

    assert TurnLedger().turn_of(_state(message), "a") is NoTurn.UNIDENTIFIED


async def test_a_call_that_already_has_an_answer_is_unidentified() -> None:
    state = _state(_message({"a": UNSAFE, "b": UNSAFE}), ToolMessage(content="done", tool_call_id="a"))

    assert TurnLedger().turn_of(state, "a") is NoTurn.UNIDENTIFIED


async def test_a_call_that_has_no_id_is_unidentified() -> None:
    assert TurnLedger().turn_of(_state(_message({"a": UNSAFE, "b": UNSAFE})), "") is NoTurn.UNIDENTIFIED


async def test_calls_written_off_are_not_missing_any_more() -> None:
    ledger = TurnLedger()
    turn = _turn(ledger, _state(_message({"a": UNSAFE, "b": UNSAFE, "c": UNSAFE})), "c")
    turn.mark_arrived("a")

    assert turn.write_off(["a", "b"]) == ["b"]
    assert turn.write_off(["a", "b"]) == []
    assert turn.unarrived_ahead_of("c", exclusive=True) == []


async def test_the_ledger_keeps_the_latest_turns_and_lets_the_oldest_go() -> None:
    ledger = TurnLedger()
    states = [_state(_message({f"a{i}": UNSAFE, f"b{i}": UNSAFE}, message_id=f"m{i}")) for i in range(KEPT_TURNS + 1)]
    turns = [_turn(ledger, state, f"a{i}") for i, state in enumerate(states)]

    assert _turn(ledger, states[-1], f"b{KEPT_TURNS}") is turns[-1]
    assert _turn(ledger, states[1], "b1") is turns[1]
    assert _turn(ledger, states[0], "b0") is not turns[0]


async def test_a_cached_turn_that_lacks_the_call_is_built_again() -> None:
    ledger = TurnLedger()
    answered = _state(_message({"a": UNSAFE, "b": UNSAFE}), ToolMessage(content="done", tool_call_id="a"))
    stale = _turn(ledger, answered, "b")

    rebuilt = _turn(ledger, _state(_message({"a": UNSAFE, "b": UNSAFE})), "a")

    assert rebuilt is not stale
    assert "a" in rebuilt


def test_a_turn_built_in_one_event_loop_is_not_handed_out_in_another() -> None:
    ledger = TurnLedger()
    state = _state(_message({"a": UNSAFE, "b": UNSAFE}))

    async def build() -> CallTurn:
        return _turn(ledger, state, "a")

    turns: list[CallTurn] = []
    for _ in range(2):
        loop = asyncio.new_event_loop()
        try:
            turns.append(loop.run_until_complete(build()))
        finally:
            loop.close()

    assert turns[0] is not turns[1]
