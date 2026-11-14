"""Which calls of one model message are still on their way to the conflict gate.

[INPUT]
- agent.security.tool_registry::resolve_safety_metadata (POS: tool safety metadata, fail-closed for undeclared tools)
- langchain_core.messages::AIMessage, ToolMessage (POS: the model message and the answers the graph state holds)

[OUTPUT]
- CallTurn: the unanswered calls of one model message in the model's order, each with an arrival signal
- NoTurn: why a call has no turn to be ordered within
- TurnLedger: finds the turn of a call in the graph state and keeps the latest turns

[POS]
The conflict gate admits calls in the order they reach it, and the calls of one model message reach it in no fixed
order. A turn tells a call which of the calls ahead of it in its message must reach the gate first, so the gate's
line ends up in the model's order. The turn is read from the graph state when the first call of a message is
dispatched and is never registered when the model answers, so a run continued by another agent instance finds it too.
"""

from __future__ import annotations

import asyncio
from collections import OrderedDict
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum

from langchain_core.messages import AIMessage, ToolMessage

from myrm_agent_harness.agent.security.tool_registry import resolve_safety_metadata

# A turn is a handful of events, so the cap only bounds memory. It is high enough that no turn is let go while its
# calls are still being dispatched, however many runs share the agent, or while its run waits for an answer.
KEPT_TURNS = 128


class NoTurn(Enum):
    """Why a call has no turn, so that the gate admits it in arrival order as it does any call.

    ``LONE_CALL``: its model message made no other call. ``UNIDENTIFIED``: its message cannot be told apart from
    others (no message id, a blank or repeated call id), or no message in the state issued the call.
    """

    LONE_CALL = "lone_call"
    UNIDENTIFIED = "unidentified"


@dataclass(frozen=True, slots=True)
class _Member:
    call_id: str
    exclusive: bool


class CallTurn:
    """The calls of one model message that had no answer yet, in the order the model made them."""

    def __init__(self, members: Sequence[_Member]) -> None:
        self._members = tuple(members)
        self._arrived = {member.call_id: asyncio.Event() for member in members}

    def __contains__(self, call_id: str) -> bool:
        return call_id in self._arrived

    def unarrived_ahead_of(self, call_id: str, *, exclusive: bool) -> list[str]:
        """The calls ahead of *call_id* that conflict with it and have not reached the gate yet."""
        ahead: list[str] = []
        for member in self._members:
            if member.call_id == call_id:
                break
            if (member.exclusive or exclusive) and not self._arrived[member.call_id].is_set():
                ahead.append(member.call_id)
        return ahead

    async def wait_until_arrived(self, call_ids: Sequence[str]) -> None:
        for call_id in call_ids:
            await self._arrived[call_id].wait()

    def mark_arrived(self, call_id: str) -> None:
        self._arrived[call_id].set()

    def write_off(self, call_ids: Sequence[str]) -> list[str]:
        """Count calls that never reached the gate as arrived so that nothing waits for them again.

        Returns the ones that were still missing.
        """
        missing = [call_id for call_id in call_ids if not self._arrived[call_id].is_set()]
        for call_id in missing:
            self._arrived[call_id].set()
        return missing


class TurnLedger:
    """Finds the turn of a call in the graph state and keeps the latest turns.

    A turn holds events that only the event loop that built it may wait on, so another loop starts with no turns.
    """

    def __init__(self) -> None:
        self._turns: OrderedDict[str, CallTurn] = OrderedDict()
        self._loop: asyncio.AbstractEventLoop | None = None

    def turn_of(self, state: object, call_id: str) -> CallTurn | NoTurn:
        """The turn *call_id* belongs to; every call of one message gets the same turn however they are scheduled."""
        messages = state.get("messages") if isinstance(state, dict) else None
        if not isinstance(messages, list):
            return NoTurn.UNIDENTIFIED
        issued = _issuing_message(messages, call_id)
        if issued is None:
            return NoTurn.UNIDENTIFIED
        position, message = issued
        if len(message.tool_calls) < 2:
            return NoTurn.LONE_CALL
        call_ids = [call["id"] or "" for call in message.tool_calls]
        if message.id is None or not all(call_ids) or len(set(call_ids)) != len(call_ids):
            return NoTurn.UNIDENTIFIED
        self._forget_turns_of_other_loops()
        turn = self._turns.get(message.id)
        if turn is None or call_id not in turn:
            turn = _unanswered_turn(message, call_ids, messages[position + 1 :])
            if call_id not in turn:
                return NoTurn.UNIDENTIFIED
            self._turns[message.id] = turn
        self._turns.move_to_end(message.id)
        while len(self._turns) > KEPT_TURNS:
            self._turns.popitem(last=False)
        return turn

    def _forget_turns_of_other_loops(self) -> None:
        loop = asyncio.get_running_loop()
        if loop is not self._loop:
            self._turns.clear()
            self._loop = loop


def _unanswered_turn(message: AIMessage, call_ids: list[str], later_messages: list[object]) -> CallTurn:
    """The turn of the calls of *message* that none of *later_messages* answers."""
    answered = {m.tool_call_id for m in later_messages if isinstance(m, ToolMessage)}
    return CallTurn(
        [
            _Member(call_id, exclusive=not resolve_safety_metadata(call["name"]).is_concurrent_safe)
            for call_id, call in zip(call_ids, message.tool_calls, strict=True)
            if call_id not in answered
        ]
    )


def _issuing_message(messages: list[object], call_id: str) -> tuple[int, AIMessage] | None:
    """The latest model message that made *call_id*, and where it is in *messages*."""
    for position in range(len(messages) - 1, -1, -1):
        message = messages[position]
        if isinstance(message, AIMessage) and any(call["id"] == call_id for call in message.tool_calls):
            return position, message
    return None
