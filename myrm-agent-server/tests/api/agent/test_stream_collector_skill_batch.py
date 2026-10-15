"""StreamContentCollector links a committed skill_manage batch to the Task Steps entry of its call."""

from __future__ import annotations

from typing import cast

from app.services.agent.streaming_support.stream_collector import StreamContentCollector
from app.services.skills.mutation_batch_stream import BATCH_ID_FIELD, build_batch_committed_event

BATCH_ID = "a1b2c3d4-e5f6-4789-a012-3456789abcde"


def _call_step_event(tool_call_id: str, tool_name: str = "skill_manage_tool") -> dict[str, object]:
    """The event the harness streams when the model calls a tool: arguments only, no result."""
    return {
        "type": "tasks_steps",
        "step_key": f"{tool_name}_tool",
        "tool_call_id": tool_call_id,
        "tool_name": tool_name,
        "data": [{"text": "save: demo"}],
        "messageId": "msg-1",
    }


def _steps(collector: StreamContentCollector) -> list[dict[str, object]]:
    return cast("list[dict[str, object]]", collector.get_snapshot()["progress_steps"])


def test_committed_batch_reaches_the_step_of_the_call_that_committed_it() -> None:
    collector = StreamContentCollector()
    collector.feed_event(_call_step_event("call-1"))

    collector.feed_event(build_batch_committed_event(BATCH_ID))

    (step,) = _steps(collector)
    assert step["tool_call_id"] == "call-1"
    assert step[BATCH_ID_FIELD] == BATCH_ID


def test_batch_of_a_later_call_does_not_overwrite_the_earlier_batch() -> None:
    other_batch = "b1b2c3d4-e5f6-4789-b012-3456789abcde"
    collector = StreamContentCollector()
    collector.feed_event(_call_step_event("call-1"))
    collector.feed_event(build_batch_committed_event(BATCH_ID))
    collector.feed_event(_call_step_event("call-2"))

    collector.feed_event(build_batch_committed_event(other_batch))

    assert [step[BATCH_ID_FIELD] for step in _steps(collector)] == [BATCH_ID, other_batch]


def test_batch_event_never_creates_a_step_of_its_own() -> None:
    collector = StreamContentCollector()
    collector.feed_event(_call_step_event("call-1", tool_name="bash_code_execute_tool"))

    collector.feed_event(build_batch_committed_event(BATCH_ID))

    (step,) = _steps(collector)
    assert BATCH_ID_FIELD not in step


def test_linked_batch_is_persisted_with_the_message_progress_steps() -> None:
    collector = StreamContentCollector()
    collector.feed_event(_call_step_event("call-1"))
    collector.feed_event(build_batch_committed_event(BATCH_ID))

    extra_data = collector.extra_data

    assert extra_data is not None
    persisted = cast("list[dict[str, object]]", extra_data["progressSteps"])
    assert persisted[0][BATCH_ID_FIELD] == BATCH_ID
