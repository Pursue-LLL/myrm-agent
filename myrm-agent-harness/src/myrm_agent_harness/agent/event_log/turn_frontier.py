"""The read side of "the log is the control flow": where a turn stood when it stopped.

[INPUT]
- myrm_agent_harness.agent.event_log.types::StructuredEvent (POS: event log data structures)
- myrm_agent_harness.agent.event_log.protocols::EventLogBackend (POS: protocol contract)

[OUTPUT]
- ToolCallOutcome: what is known about one tool call
- ToolCallState: the state of one tool call
- TurnFrontier: what a turn had already done when it stopped
- derive_turn_frontier: derive the frontier from the events of one turn
- load_turn_frontier: read a turn's events from a backend and derive the frontier

[POS]
Read side of the event log, for the recovery decision: given a turn, which tool calls had
already finished, which one was still in flight, and how many model calls had been made.

**The frontier never under-reports a side effect.** A tool call that started but has no
terminal event is reported as `IN_FLIGHT`, because the crash may have happened after the tool
ran: the caller must not repeat such a call blindly. This is the same "unknown, do not
repeat" semantics the durable tool ledger uses (`runtime/tool_ledger`).

**Path decision (2026-10-21 review, verified against the code)**: the frontier is derived from
the event log, not from `agent/event_stream/`. The reasons are concrete:

* the event log already records `tool_start` / `tool_end` / `tool_failure` / `tool_cancelled`
  with a `tool_call_id`, and `trace_builder` / `_pairing` already pair them;
* the event log's backend already offers the durability barrier a recovery decision needs
  (`flush()` takes the write lock so every in-flight append has reached the filesystem, and
  `durable_atomic_writer` adds fsync, advisory locking and torn-tail repair);
* the `agent/event_stream/` SQLite projector models **sessions, messages, parts and events**
  and contains **no tool concept at all**, so that path would first have to invent the very
  projection the frontier needs.

**What this module cannot know**: the log has no turn marker — `StructuredEvent` carries
`sequence`, `timestamp`, `event_type`, `session_id` and the payload, and nothing else. A turn
is therefore delimited by a **sequence range**, which the caller supplies; and because the
logger batches writes (50 events / 0.5 s), an intent may not be on disk when the crash
happens. That is why `may_have_side_effects` is the property a caller must consult, and why
the flush barrier before dispatching a side-effecting tool (the "intent durability" work) is
a prerequisite for treating this frontier as authoritative.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum

from myrm_agent_harness.agent.event_log.protocols import EventLogBackend
from myrm_agent_harness.agent.event_log.types import StructuredEvent

TOOL_START = "tool_start"
TOOL_END = "tool_end"
TOOL_FAILURE = "tool_failure"
TOOL_CANCELLED = "tool_cancelled"
LLM_REQUEST = "llm_request"

_TERMINAL_OUTCOMES: dict[str, "ToolCallOutcome"] = {}


class ToolCallOutcome(str, Enum):
    """What is known about one tool call."""

    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    IN_FLIGHT = "in_flight"


_TERMINAL_OUTCOMES = {
    TOOL_END: ToolCallOutcome.COMPLETED,
    TOOL_FAILURE: ToolCallOutcome.FAILED,
    TOOL_CANCELLED: ToolCallOutcome.CANCELLED,
}


@dataclass(frozen=True)
class ToolCallState:
    """The state of one tool call."""

    tool_name: str
    outcome: ToolCallOutcome
    tool_call_id: str | None = None
    start_sequence: int | None = None
    end_sequence: int | None = None


@dataclass(frozen=True)
class TurnFrontier:
    """What a turn had already done when it stopped."""

    session_id: str
    turn_id: str
    tool_calls: tuple[ToolCallState, ...] = ()
    llm_request_count: int = 0
    last_sequence: int | None = None

    @property
    def completed_tool_calls(self) -> tuple[ToolCallState, ...]:
        """Tool calls that finished."""
        return tuple(call for call in self.tool_calls if call.outcome is not ToolCallOutcome.IN_FLIGHT)

    @property
    def in_flight_tool_calls(self) -> tuple[ToolCallState, ...]:
        """Tool calls that started but never reported an outcome."""
        return tuple(call for call in self.tool_calls if call.outcome is ToolCallOutcome.IN_FLIGHT)

    @property
    def may_have_side_effects(self) -> bool:
        """True when a tool call's outcome is unknown: it may have run, so do not repeat it."""
        return bool(self.in_flight_tool_calls)


def _payload(event: StructuredEvent) -> dict[str, object]:
    """The event payload as a plain mapping."""
    data = event.data
    if isinstance(data, dict):
        return data
    getter = getattr(data, "model_dump", None)
    if callable(getter):
        dumped = getter()
        if isinstance(dumped, dict):
            return dumped
    return {}


def _text(payload: dict[str, object], key: str) -> str | None:
    """A string field of the payload, or None."""
    value = payload.get(key)
    return value if isinstance(value, str) and value.strip() else None


def derive_turn_frontier(
    session_id: str,
    turn_id: str,
    events: Sequence[StructuredEvent],
    *,
    since_sequence: int | None = None,
) -> TurnFrontier:
    """Derive the frontier of one turn from its events.

    `since_sequence` delimits the turn: only events after it belong to this turn. The caller
    supplies it because the event log carries no turn marker of its own.
    """
    ordered = sorted(events, key=lambda event: event.sequence)
    if since_sequence is not None:
        ordered = [event for event in ordered if event.sequence > since_sequence]

    started: dict[str, ToolCallState] = {}
    by_name: dict[str, list[str]] = {}
    calls: list[ToolCallState] = []
    llm_requests = 0
    last_sequence: int | None = None

    for event in ordered:
        last_sequence = event.sequence
        payload = _payload(event)
        event_type = event.event_type

        if event_type == LLM_REQUEST:
            llm_requests += 1
            continue

        if event_type == TOOL_START:
            tool_name = _text(payload, "tool_name") or "(unknown)"
            tool_call_id = _text(payload, "tool_call_id")
            key = tool_call_id or f"__name__:{tool_name}:{len(by_name.get(tool_name, []))}"
            state = ToolCallState(
                tool_name=tool_name,
                outcome=ToolCallOutcome.IN_FLIGHT,
                tool_call_id=tool_call_id,
                start_sequence=event.sequence,
            )
            started[key] = state
            by_name.setdefault(tool_name, []).append(key)
            continue

        outcome = _TERMINAL_OUTCOMES.get(event_type)
        if outcome is None:
            continue

        tool_name = _text(payload, "tool_name") or "(unknown)"
        tool_call_id = _text(payload, "tool_call_id")

        matched: ToolCallState | None = None
        if tool_call_id is not None and tool_call_id in started:
            matched = started.pop(tool_call_id)
            queue = by_name.get(matched.tool_name)
            if queue and tool_call_id in queue:
                queue.remove(tool_call_id)
        else:
            queue = by_name.get(tool_name) or []
            while queue:
                key = queue.pop(0)
                candidate = started.pop(key, None)
                if candidate is not None:
                    matched = candidate
                    break

        if matched is None:
            # The intent was never recorded (or was lost before the flush): the call still
            # happened, so it is reported as finished — never as "it did not run".
            calls.append(
                ToolCallState(
                    tool_name=tool_name,
                    outcome=outcome,
                    tool_call_id=tool_call_id,
                    end_sequence=event.sequence,
                )
            )
            continue

        calls.append(
            ToolCallState(
                tool_name=matched.tool_name,
                outcome=outcome,
                tool_call_id=matched.tool_call_id or tool_call_id,
                start_sequence=matched.start_sequence,
                end_sequence=event.sequence,
            )
        )

    calls.extend(started.values())
    return TurnFrontier(
        session_id=session_id,
        turn_id=turn_id,
        tool_calls=tuple(calls),
        llm_request_count=llm_requests,
        last_sequence=last_sequence,
    )


async def load_turn_frontier(
    backend: EventLogBackend,
    session_id: str,
    turn_id: str,
    *,
    since_sequence: int | None = None,
) -> TurnFrontier:
    """Read a turn's events from a backend and derive its frontier."""
    events = await backend.get_events(session_id)
    return derive_turn_frontier(session_id, turn_id, events, since_sequence=since_sequence)
