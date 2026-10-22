"""Tests for the turn frontier — the read side of "the log is the control flow".

The frontier decides what a crashed turn had already done. The property that matters is
that it never under-reports a side effect: a tool call whose outcome is unknown must be
reported as in flight, so the caller does not repeat it.
"""

from __future__ import annotations

from typing import Any

from myrm_agent_harness.agent.event_log.turn_frontier import (
    ToolCallOutcome,
    derive_turn_frontier,
)
from myrm_agent_harness.agent.event_log.types import EventPayload, StructuredEvent


def _event(sequence: int, event_type: str, **data: Any) -> StructuredEvent:
    return StructuredEvent(
        sequence=sequence,
        timestamp=float(sequence),
        event_type=event_type,
        session_id="session-1",
        data=EventPayload(**data),
    )


def test_a_turn_with_no_events_has_an_empty_frontier() -> None:
    frontier = derive_turn_frontier("session-1", "turn-1", [])
    assert frontier.tool_calls == ()
    assert frontier.may_have_side_effects is False
    assert frontier.last_sequence is None


def test_a_finished_tool_call_is_reported_as_completed() -> None:
    events = [
        _event(1, "tool_start", tool_name="read_file", tool_call_id="call-1"),
        _event(2, "tool_end", tool_name="read_file", tool_call_id="call-1"),
    ]
    frontier = derive_turn_frontier("session-1", "turn-1", events)
    assert len(frontier.tool_calls) == 1
    assert frontier.tool_calls[0].outcome is ToolCallOutcome.COMPLETED
    assert frontier.tool_calls[0].start_sequence == 1
    assert frontier.tool_calls[0].end_sequence == 2
    assert frontier.may_have_side_effects is False


def test_a_failed_tool_call_is_reported_as_failed() -> None:
    events = [
        _event(1, "tool_start", tool_name="refund", tool_call_id="call-1"),
        _event(2, "tool_failure", tool_name="refund", tool_call_id="call-1"),
    ]
    frontier = derive_turn_frontier("session-1", "turn-1", events)
    assert frontier.tool_calls[0].outcome is ToolCallOutcome.FAILED


def test_a_cancelled_tool_call_is_reported_as_cancelled() -> None:
    events = [
        _event(1, "tool_start", tool_name="read_file", tool_call_id="call-1"),
        _event(2, "tool_cancelled", tool_name="read_file", tool_call_id="call-1"),
    ]
    frontier = derive_turn_frontier("session-1", "turn-1", events)
    assert frontier.tool_calls[0].outcome is ToolCallOutcome.CANCELLED


def test_a_tool_call_without_an_outcome_is_in_flight() -> None:
    """The crash may have happened after the tool ran: the caller must not repeat it."""
    events = [_event(1, "tool_start", tool_name="refund", tool_call_id="call-1")]
    frontier = derive_turn_frontier("session-1", "turn-1", events)
    assert frontier.tool_calls[0].outcome is ToolCallOutcome.IN_FLIGHT
    assert frontier.may_have_side_effects is True


def test_concurrent_calls_of_the_same_tool_are_paired_by_id() -> None:
    events = [
        _event(1, "tool_start", tool_name="read_file", tool_call_id="call-1"),
        _event(2, "tool_start", tool_name="read_file", tool_call_id="call-2"),
        _event(3, "tool_end", tool_name="read_file", tool_call_id="call-2"),
        _event(4, "tool_end", tool_name="read_file", tool_call_id="call-1"),
    ]
    frontier = derive_turn_frontier("session-1", "turn-1", events)
    by_id = {call.tool_call_id: call for call in frontier.tool_calls}
    assert by_id["call-1"].start_sequence == 1
    assert by_id["call-2"].start_sequence == 2
    assert all(call.outcome is ToolCallOutcome.COMPLETED for call in frontier.tool_calls)


def test_a_terminal_event_without_a_start_still_counts_as_happened() -> None:
    """The intent may have been lost before the flush: the call must not be reported as never-run."""
    events = [_event(2, "tool_end", tool_name="read_file", tool_call_id="call-1")]
    frontier = derive_turn_frontier("session-1", "turn-1", events)
    assert len(frontier.tool_calls) == 1
    assert frontier.tool_calls[0].outcome is ToolCallOutcome.COMPLETED
    assert frontier.may_have_side_effects is False


def test_model_calls_are_counted() -> None:
    events = [
        _event(1, "llm_request", model="gpt-4o-mini"),
        _event(2, "tool_start", tool_name="read_file", tool_call_id="call-1"),
        _event(3, "tool_end", tool_name="read_file", tool_call_id="call-1"),
        _event(4, "llm_request", model="gpt-4o-mini"),
    ]
    frontier = derive_turn_frontier("session-1", "turn-1", events)
    assert frontier.llm_request_count == 2
    assert frontier.last_sequence == 4


def test_the_sequence_range_delimits_the_turn() -> None:
    events = [
        _event(1, "tool_start", tool_name="read_file", tool_call_id="old"),
        _event(2, "tool_end", tool_name="read_file", tool_call_id="old"),
        _event(3, "tool_start", tool_name="refund", tool_call_id="new"),
    ]
    frontier = derive_turn_frontier("session-1", "turn-1", events, since_sequence=2)
    assert [call.tool_call_id for call in frontier.tool_calls] == ["new"]
    assert frontier.may_have_side_effects is True


def test_events_are_read_in_sequence_order_whatever_the_order_they_arrive_in() -> None:
    events = [
        _event(2, "tool_end", tool_name="read_file", tool_call_id="call-1"),
        _event(1, "tool_start", tool_name="read_file", tool_call_id="call-1"),
    ]
    frontier = derive_turn_frontier("session-1", "turn-1", events)
    assert frontier.tool_calls[0].outcome is ToolCallOutcome.COMPLETED
    assert frontier.tool_calls[0].start_sequence == 1


def test_a_tool_call_without_an_id_falls_back_to_the_oldest_of_that_name() -> None:
    events = [
        _event(1, "tool_start", tool_name="read_file"),
        _event(2, "tool_start", tool_name="read_file"),
        _event(3, "tool_end", tool_name="read_file"),
    ]
    frontier = derive_turn_frontier("session-1", "turn-1", events)
    outcomes = [call.outcome for call in frontier.tool_calls]
    assert outcomes.count(ToolCallOutcome.COMPLETED) == 1
    assert outcomes.count(ToolCallOutcome.IN_FLIGHT) == 1
