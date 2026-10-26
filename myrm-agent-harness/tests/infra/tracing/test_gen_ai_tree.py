"""The GenAI span tree: invoke_agent -> chat / execute_tool, with sub-agents as subtrees."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import pytest
from opentelemetry import trace
from opentelemetry.trace import SpanKind, StatusCode

from myrm_agent_harness.infra.tracing.gen_ai import AgentRunSpan, ModelCall, execute_tool_span

from .conftest import MemoryTelemetry

RESPONSE = {
    "model": "gpt-x-2025-01",
    "choices": [{"finish_reason": "stop", "message": {"role": "assistant", "content": "done"}}],
    "usage": {"prompt_tokens": 20, "completion_tokens": 5},
}


def _agent(agent_type: str = "SkillAgent", **context: str) -> AgentRunSpan:
    return AgentRunSpan(
        agent_type=agent_type,
        query="hello",
        context_values=context or {"session_id": "conv-1", "agent_id": "agent-1"},
        message_id="msg-1",
    )


def _chat(model: str = "gpt-x") -> None:
    call = ModelCall(model=model, provider="openai", stream=False, params={}, message_dicts=[])
    call.begin(1)
    call.finish(RESPONSE)
    call.close()


async def _run(agent: AgentRunSpan, events: AsyncIterator[str]) -> list[str]:
    seen: list[str] = []
    try:
        async for event in agent.scope(events):
            seen.append(event)
    finally:
        agent.end()
    return seen


async def test_a_run_forms_the_standard_tree(telemetry: MemoryTelemetry) -> None:
    async def events() -> AsyncIterator[str]:
        yield "started"
        _chat()
        with execute_tool_span(name="web_search", call_id="call-1", arguments={"query": "q"}):
            pass
        yield "finished"

    assert await _run(_agent(), events()) == ["started", "finished"]

    root = telemetry.span("invoke_agent SkillAgent")
    chat = telemetry.span("chat gpt-x")
    tool = telemetry.span("execute_tool web_search")
    assert telemetry.parent_name(root) is None
    assert telemetry.parent_name(chat) == root.name
    assert telemetry.parent_name(tool) == root.name
    assert (root.kind, chat.kind, tool.kind) == (SpanKind.INTERNAL, SpanKind.CLIENT, SpanKind.INTERNAL)
    assert dict(root.attributes or {}) == {
        "gen_ai.operation.name": "invoke_agent",
        "gen_ai.agent.name": "SkillAgent",
        "gen_ai.conversation.id": "conv-1",
        "gen_ai.agent.id": "agent-1",
        "agent.message_id": "msg-1",
        "agent.status": "completed",
    }
    assert dict(tool.attributes or {}) == {
        "gen_ai.operation.name": "execute_tool",
        "gen_ai.tool.name": "web_search",
        "gen_ai.tool.type": "function",
        "gen_ai.tool.call.id": "call-1",
    }


async def test_the_run_span_is_not_current_while_the_consumer_holds_control(telemetry: MemoryTelemetry) -> None:
    async def events() -> AsyncIterator[str]:
        yield "one"
        yield "two"

    agent = _agent()
    inside_consumer: list[bool] = []
    async for _ in agent.scope(events()):
        inside_consumer.append(trace.get_current_span() is agent.span)
    agent.end()

    assert inside_consumer == [False, False]


async def test_the_run_span_is_current_inside_each_step(telemetry: MemoryTelemetry) -> None:
    agent = _agent()
    seen: list[bool] = []

    async def events() -> AsyncIterator[str]:
        seen.append(trace.get_current_span() is agent.span)
        yield "one"
        seen.append(trace.get_current_span() is agent.span)
        yield "two"

    await _run(agent, events())

    assert seen == [True, True]


async def test_parallel_tools_and_spawned_tasks_attach_to_the_run(telemetry: MemoryTelemetry) -> None:
    async def tool(name: str) -> None:
        with execute_tool_span(name=name, call_id=None, arguments={}):
            await asyncio.sleep(0.01)

    async def executor_work() -> None:
        await asyncio.gather(tool("read_file"), tool("grep"))

    async def events() -> AsyncIterator[str]:
        await asyncio.create_task(executor_work())
        yield "done"

    await _run(_agent(), events())

    root = telemetry.span("invoke_agent SkillAgent")
    for name in ("execute_tool read_file", "execute_tool grep"):
        assert telemetry.parent_name(telemetry.span(name)) == root.name


async def test_a_sub_agent_is_a_subtree_of_the_tool_that_ran_it(telemetry: MemoryTelemetry) -> None:
    async def child_events() -> AsyncIterator[str]:
        _chat("gpt-child")
        yield "child step"

    async def events() -> AsyncIterator[str]:
        with execute_tool_span(name="delegate", call_id="c1", arguments={}):
            await _run(_agent("ChildAgent", session_id="conv-1", agent_id="agent-2"), child_events())
        yield "parent step"

    await _run(_agent(), events())

    tool = telemetry.span("execute_tool delegate")
    child = telemetry.span("invoke_agent ChildAgent")
    assert telemetry.parent_name(tool) == "invoke_agent SkillAgent"
    assert telemetry.parent_name(child) == tool.name
    assert telemetry.parent_name(telemetry.span("chat gpt-child")) == child.name


async def test_a_failed_run_records_the_error_class_and_never_the_message(telemetry: MemoryTelemetry) -> None:
    async def events() -> AsyncIterator[str]:
        yield "started"
        raise ValueError("secret prompt text")

    with pytest.raises(ValueError, match="secret"):
        await _run(_agent(), events())

    root = telemetry.span("invoke_agent SkillAgent")
    assert root.attributes is not None
    assert root.attributes["agent.status"] == "error"
    assert root.attributes["error.type"] == "ValueError"
    assert root.status.status_code is StatusCode.ERROR
    assert root.status.description == "ValueError"
    assert not root.events
    assert "secret" not in str(root.attributes)


async def test_a_cancelled_run_is_cancelled_not_an_error(telemetry: MemoryTelemetry) -> None:
    started = asyncio.Event()

    async def events() -> AsyncIterator[str]:
        started.set()
        await asyncio.sleep(30)
        yield "never"

    task = asyncio.create_task(_run(_agent(), events()))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    root = telemetry.span("invoke_agent SkillAgent")
    assert root.attributes is not None
    assert root.attributes["agent.status"] == "cancelled"
    assert root.status.status_code is StatusCode.UNSET


async def test_a_consumer_that_stops_early_leaves_a_cancelled_span(telemetry: MemoryTelemetry) -> None:
    async def events() -> AsyncIterator[str]:
        yield "one"
        yield "two"

    agent = _agent()
    async for _ in agent.scope(events()):
        break
    agent.end()

    root = telemetry.span("invoke_agent SkillAgent")
    assert root.attributes is not None
    assert root.attributes["agent.status"] == "cancelled"


async def test_the_first_outcome_wins(telemetry: MemoryTelemetry) -> None:
    agent = _agent()
    agent.settle("completed")
    agent.settle("error", error_type="Late")
    agent.end()

    root = telemetry.span("invoke_agent SkillAgent")
    assert root.attributes is not None
    assert root.attributes["agent.status"] == "completed"
    assert "error.type" not in root.attributes


async def test_a_tool_failure_is_marked_with_its_class_and_the_exception_propagates(telemetry: MemoryTelemetry) -> None:
    with pytest.raises(RuntimeError, match="boom"), execute_tool_span(name="shell", call_id=None, arguments={}):
        raise RuntimeError("boom with secret")

    tool = telemetry.span("execute_tool shell")
    assert tool.attributes is not None
    assert tool.attributes["error.type"] == "RuntimeError"
    assert tool.status.description == "RuntimeError"
    assert not tool.events
