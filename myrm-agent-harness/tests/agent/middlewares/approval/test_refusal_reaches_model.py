"""What the model is told when a tool call is refused, through the agent's own middleware stack.

A refused call stays in the AI message and is answered by an error ToolMessage, so the model reads who refused it
and why as the result of its own call, and the dangling-call repair finds no orphan to drop before the next model
call.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from langchain.agents import create_agent
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import tool
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.errors import GraphRecursionError
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command
from pydantic import Field

from myrm_agent_harness.agent._internals._agent_build import build_middlewares, create_registry
from myrm_agent_harness.agent.middlewares._session_context import (
    set_approval_session,
    set_approval_user_id,
    set_security_config,
    set_workspace_root,
)
from myrm_agent_harness.agent.middlewares.approval.helpers import clear_all_session_denials_for_tests
from myrm_agent_harness.agent.security.types import PrivacyPolicy, SecurityConfig

RAN: list[str] = []
THREAD = {"configurable": {"thread_id": "t"}}


@tool
def step(text: str = "") -> str:
    """Record that the step ran."""
    RAN.append(text)
    return "done"


@tool
def ask_question_tool(questions: str) -> str:
    """Answer for the user."""
    return "asked"


class ScriptedModel(BaseChatModel):
    """Answers from a script and records the messages each call was sent as ``(type, text)`` pairs."""

    script: list[AIMessage]
    calls: list[list[tuple[str, str]]] = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def bind_tools(self, tools: object, **kwargs: object) -> ScriptedModel:
        return self

    def _generate(
        self, messages: list[BaseMessage], stop: list[str] | None = None, run_manager: object = None, **kwargs: object
    ) -> ChatResult:
        self.calls.append([(type(m).__name__, str(m.content)) for m in messages])
        served = len(self.calls)
        reply = self.script[min(served, len(self.script)) - 1]
        if served > len(self.script):
            # A repeated reply is a new message with new call ids, as a model that retries would produce.
            retry = [{**call, "id": f"{call['id']}-{served}"} for call in reply.tool_calls]
            reply = AIMessage(content=reply.content, tool_calls=retry)
        return ChatResult(generations=[ChatGeneration(message=reply)])


def _calls(*names_and_ids: tuple[str, str, dict[str, str]]) -> AIMessage:
    return AIMessage(content="", tool_calls=[{"id": i, "name": n, "args": a} for i, n, a in names_and_ids])


def _agent(script: list[AIMessage]) -> tuple[ScriptedModel, CompiledStateGraph]:
    model = ScriptedModel(script=script)
    return model, create_agent(
        model,
        tools=[step, ask_question_tool],
        middleware=build_middlewares(create_registry(), []),
        checkpointer=InMemorySaver(),
    )


def _tool_texts(call: list[tuple[str, str]]) -> list[str]:
    return [text for kind, text in call if kind == ToolMessage.__name__]


def _assert_every_call_is_answered_once(messages: list[BaseMessage]) -> None:
    answers = [m.tool_call_id for m in messages if isinstance(m, ToolMessage)]
    asked = [call["id"] for m in messages if isinstance(m, AIMessage) for call in m.tool_calls]
    assert sorted(answers) == sorted(asked)


@pytest.fixture(autouse=True)
def _session(tmp_path: Path) -> Iterator[None]:
    RAN.clear()
    clear_all_session_denials_for_tests()
    set_security_config(SecurityConfig(yolo_mode_enabled=False, privacy_policy=PrivacyPolicy(enabled=False)))
    set_workspace_root(str(tmp_path))
    set_approval_session("web-session")
    set_approval_user_id("user-1")
    yield
    set_security_config(None)
    set_workspace_root("")
    set_approval_session("")
    set_approval_user_id("")
    clear_all_session_denials_for_tests()


async def _ask_then_resume(agent: CompiledStateGraph, resume: dict[str, object]) -> dict[str, object]:
    result = await agent.ainvoke({"messages": [HumanMessage(content="go")]}, THREAD)
    assert result["__interrupt__"]
    return await agent.ainvoke(Command(resume=resume), THREAD)


async def test_the_reason_a_user_gives_for_refusing_reaches_the_model() -> None:
    first = _calls(("s1", "step", {"text": "a"}))
    model, agent = _agent([first, AIMessage(content="understood")])

    result = await _ask_then_resume(agent, {"decisions": [{"type": "reject", "feedback": "Too risky, use a dry run"}]})

    assert RAN == []
    assert len(model.calls) == 2
    [refusal] = _tool_texts(model.calls[1])
    assert "Action rejected by user: Too risky, use a dry run" in refusal
    assert "The user declined this action" in refusal
    assert result["messages"][-1].content == "understood"
    _assert_every_call_is_answered_once(result["messages"])


async def test_a_batch_runs_the_approved_call_and_tells_the_model_why_the_other_did_not() -> None:
    first = _calls(("s1", "step", {"text": "a"}), ("s2", "step", {"text": "b"}))
    model, agent = _agent([first, AIMessage(content="ok")])

    result = await _ask_then_resume(
        agent, {"decisions": [{"type": "approve"}, {"type": "reject", "feedback": "not b"}]}
    )

    assert RAN == ["a"]
    texts = _tool_texts(model.calls[1])
    assert any(t == "done" for t in texts)
    assert any("Action rejected by user: not b" in t for t in texts)
    _assert_every_call_is_answered_once(result["messages"])


async def test_an_edited_call_runs_with_the_edit_while_a_refused_one_is_kept_and_answered() -> None:
    first = _calls(("s1", "step", {"text": "a"}), ("s2", "step", {"text": "b"}))
    model, agent = _agent([first, AIMessage(content="ok")])

    result = await _ask_then_resume(
        agent, {"decisions": [{"type": "edit", "args": {"text": "edited"}}, {"type": "reject"}]}
    )

    assert RAN == ["edited"]
    assert any("Action rejected by user: User rejected this action." in t for t in _tool_texts(model.calls[1]))
    _assert_every_call_is_answered_once(result["messages"])


async def test_an_approval_that_timed_out_says_nobody_answered() -> None:
    first = _calls(("s1", "step", {"text": "a"}))
    model, agent = _agent([first, AIMessage(content="ok")])

    await _ask_then_resume(
        agent, {"decision": "reject", "feedback": "Auto-rejected: approval timeout (300s)", "timed_out": True}
    )

    assert RAN == []
    [refusal] = _tool_texts(model.calls[1])
    assert "timed out" in refusal
    assert "did not answer in time" in refusal
    assert "rejected by user" not in refusal.lower()
    assert "declined" not in refusal


async def test_a_scheduled_job_that_cannot_ask_gets_the_denial_and_finishes_its_report() -> None:
    set_approval_session("cron:job-1")
    model, agent = _agent([_calls(("s1", "step", {"text": "a"})), AIMessage(content="report: step was blocked")])

    result = await agent.ainvoke({"messages": [HumanMessage(content="run the job")]}, THREAD)

    assert "__interrupt__" not in result
    assert RAN == []
    assert len(model.calls) == 2
    assert any("cron" in t.lower() for t in _tool_texts(model.calls[1]))
    assert result["messages"][-1].content == "report: step was blocked"
    _assert_every_call_is_answered_once(result["messages"])


async def test_a_job_that_keeps_retrying_a_denied_call_is_told_to_stop_and_is_bounded() -> None:
    set_approval_session("cron:job-2")
    model, agent = _agent([_calls(("s1", "step", {"text": "a"}))])

    with pytest.raises(GraphRecursionError):
        await agent.ainvoke({"messages": [HumanMessage(content="run the job")]}, {**THREAD, "recursion_limit": 40})

    assert RAN == []
    assert 3 <= len(model.calls) <= 40
    assert "consecutive denials for this scheduled job" in _tool_texts(model.calls[-1])[-1]
    assert "explicit human approval" not in _tool_texts(model.calls[-1])[-1]


async def test_a_tool_called_next_to_ask_question_tool_is_refused_in_a_way_the_model_can_read() -> None:
    first = _calls(("q1", "ask_question_tool", {"questions": "which?"}), ("s1", "step", {"text": "a"}))
    model, agent = _agent([first, AIMessage(content="ok")])

    result = await agent.ainvoke({"messages": [HumanMessage(content="ask and step")]}, THREAD)

    assert "__interrupt__" not in result
    assert RAN == []
    assert any("only tool in this turn" in t for t in _tool_texts(model.calls[1]))
    _assert_every_call_is_answered_once(result["messages"])
