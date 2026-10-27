"""A runtime hook's call is not shown to the user as a task step.

The completion guard rewrites a completion attempt into a call of its ``_completion_check`` hook. The hook is the
harness talking to the model, not work the user asked for: a ``tasks_steps`` event for it would put an unlabeled
step into the user's task list, carrying the guard's internal reason (on a forced finish, the whole directive as an
error step).
"""

from __future__ import annotations

import pytest
from langchain_core.messages import AIMessage, ToolMessage

from myrm_agent_harness.agent.orchestration.hooks import COMPLETION_CHECK_TOOL_NAME
from myrm_agent_harness.agent.streaming.event_handlers import process_updates_chunk
from myrm_agent_harness.agent.streaming.types import AgentEventType
from myrm_agent_harness.agent.types import AgentRunStatistics


def _call(name: str, call_id: str, **args: object) -> dict[str, object]:
    return {"name": name, "args": args, "id": call_id, "type": "tool_call"}


async def _events(*calls: dict[str, object]) -> tuple[list[dict[str, object]], AgentRunStatistics]:
    stats = AgentRunStatistics()
    message = AIMessage(content="", tool_calls=list(calls))
    events = [event async for event in process_updates_chunk({"model": {"messages": [message]}}, stats, "msg_1")]
    return events, stats


async def _result_events(name: str, content: str, status: str) -> list[dict[str, object]]:
    message = ToolMessage(content=content, name=name, tool_call_id="call_1", status=status)
    chunk = {"tools": {"messages": [message]}}
    return [event async for event in process_updates_chunk(chunk, AgentRunStatistics(), "msg_1")]


def _steps(events: list[dict[str, object]]) -> list[dict[str, object]]:
    return [event for event in events if event["type"] == AgentEventType.TASKS_STEPS.value]


@pytest.mark.asyncio
async def test_a_guard_hook_call_emits_no_task_step() -> None:
    events, _ = await _events(
        _call(COMPLETION_CHECK_TOOL_NAME, "call_hook", deliverable_write_reason="Substantial unpersisted deliverables")
    )

    assert _steps(events) == []


@pytest.mark.asyncio
async def test_the_hook_call_is_still_counted_as_a_tool_call() -> None:
    _, stats = await _events(_call(COMPLETION_CHECK_TOOL_NAME, "call_hook"))

    assert stats.tool_call_count == 1


@pytest.mark.asyncio
async def test_a_real_tool_call_next_to_a_hook_call_still_emits_its_step() -> None:
    events, stats = await _events(
        _call(COMPLETION_CHECK_TOOL_NAME, "call_hook"),
        _call("file_write_tool", "call_write", path="a.py", content="x"),
    )

    steps = _steps(events)
    assert [step["tool_name"] for step in steps] == ["file_write_tool"]
    assert stats.tool_call_count == 2


@pytest.mark.asyncio
async def test_a_failed_guard_hook_result_emits_no_error_step() -> None:
    events = await _result_events(COMPLETION_CHECK_TOOL_NAME, "CRITICAL SYSTEM DIRECTIVE: verify first", "error")

    assert events == []


@pytest.mark.asyncio
async def test_a_failed_real_tool_result_still_emits_its_error_step() -> None:
    events = await _result_events("bash_code_execute_tool", "Error: exit status 1", "error")

    assert [(event["type"], event["tool_name"], event["status"]) for event in events] == [
        (AgentEventType.TASKS_STEPS.value, "bash_code_execute_tool", "error")
    ]
