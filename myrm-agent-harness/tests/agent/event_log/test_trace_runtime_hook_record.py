"""The trace keeps a runtime hook's invocation without any ``tasks_steps`` event for it.

The streaming layer no longer emits a task step for the completion guard's ``_completion_check`` hook; the
``tool_start``/``tool_end`` lifecycle pair published for every tool execution is then the hook's only trace
record, and it is enough: one successful call with its timing and id.
"""

from __future__ import annotations

import pytest

from myrm_agent_harness.agent.event_log.trace_builder import build_trace
from myrm_agent_harness.agent.event_log.types import EventFilter, StructuredEvent
from myrm_agent_harness.agent.orchestration.hooks import COMPLETION_CHECK_TOOL_NAME


class _Backend:
    def __init__(self, events: list[StructuredEvent]) -> None:
        self._events = events

    async def get_events(self, session_id: str, event_filter: EventFilter | None = None) -> list[StructuredEvent]:
        return list(self._events)


def _event(seq: int, event_type: str, **data: object) -> StructuredEvent:
    return StructuredEvent(
        sequence=seq, timestamp=1_700_000_000.0 + seq, event_type=event_type, session_id="sess-1", data=dict(data)
    )


@pytest.mark.asyncio
async def test_a_hook_call_without_a_task_step_is_one_successful_record() -> None:
    events = [
        _event(1, "session_start"),
        _event(
            2,
            "tool_start",
            tool_name=COMPLETION_CHECK_TOOL_NAME,
            tool_call_id="call_hook",
            args={"evidence_reason": "x"},
        ),
        _event(3, "tool_end", tool_name=COMPLETION_CHECK_TOOL_NAME, tool_call_id="call_hook", duration_ms=3.0),
        _event(4, "session_end"),
    ]

    trace = await build_trace(_Backend(events), "sess-1")  # type: ignore[arg-type]

    assert [(tc.tool_name, tc.tool_call_id, tc.success) for tc in trace.tool_calls] == [
        (COMPLETION_CHECK_TOOL_NAME, "call_hook", True)
    ]
