"""A scheduled job's agents run to their answer through the real graph, with nobody to answer an approval.

With the shipped middleware stack on a real LangGraph agent, in the job's own agent and in an agent it delegated to
(whose session key is a task id, not a cron key):
1. A call the job's declaration approves runs.
2. A call the declaration does not cover is refused, and the run goes on to its answer.
3. Neither leaves the run paused at an approval: the result carries no interrupt.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from langchain.agents import create_agent
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import tool
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph.state import CompiledStateGraph

import myrm_agent_harness.agent.security.approval_flow as approval_flow
from myrm_agent_harness.agent._internals._agent_build import build_middlewares, create_registry
from myrm_agent_harness.agent.middlewares._session_context import set_security_config
from myrm_agent_harness.agent.middlewares.approval import get_approval_rate_limiter, set_approval_session
from myrm_agent_harness.agent.middlewares.approval.batch_processor import register_security_reviewer
from myrm_agent_harness.agent.middlewares.approval.helpers import clear_all_session_denials_for_tests
from myrm_agent_harness.agent.security.audit import reset_audit_log
from myrm_agent_harness.agent.security.channel_presets import build_channel_security_config
from myrm_agent_harness.agent.security.guards.taint_tracker import reset_taint_tracker

_RUNS = pytest.mark.parametrize("session", ["cron:job-1", "task-7"], ids=["job-agent", "delegated-agent"])


@tool
def mcp__notes__create_note(title: str) -> str:
    """Create a note."""
    return f"created {title}"


class CallsTheToolOnce(BaseChatModel):
    """Calls the note tool in its first turn, then answers."""

    served: int = 0

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def bind_tools(self, tools: object, **kwargs: object) -> CallsTheToolOnce:
        return self

    def _generate(
        self, messages: list[BaseMessage], stop: list[str] | None = None, run_manager: object = None, **kwargs: object
    ) -> ChatResult:
        if self.served == 0:
            call = {"id": "c0", "name": "mcp__notes__create_note", "args": {"title": "x"}}
            reply = AIMessage(content="", tool_calls=[call])
        else:
            reply = AIMessage(content="done")
        self.served += 1
        return ChatResult(generations=[ChatGeneration(message=reply)])


@pytest.fixture(autouse=True)
def _isolation() -> Iterator[None]:
    approval_flow._allowlist = approval_flow.Allowlist()
    reset_taint_tracker()
    reset_audit_log()
    clear_all_session_denials_for_tests()
    get_approval_rate_limiter().reset(None)
    register_security_reviewer(None)
    yield
    register_security_reviewer(None)
    reset_taint_tracker()


def _agent() -> CompiledStateGraph:
    return create_agent(
        CallsTheToolOnce(),
        tools=[mcp__notes__create_note],
        middleware=build_middlewares(create_registry(), []),
        checkpointer=InMemorySaver(),
    )


async def _run(session: str, *, declared: bool) -> dict[str, object]:
    set_security_config(
        build_channel_security_config("cron", declared_capabilities=("mcp_invoke",) if declared else ())
    )
    set_approval_session(session)
    return await _agent().ainvoke(
        {"messages": [HumanMessage(content="note it")]}, {"configurable": {"thread_id": session}}
    )


def _messages(result: dict[str, object]) -> list[BaseMessage]:
    messages = result["messages"]
    assert isinstance(messages, list)
    return messages


@_RUNS
async def test_a_declared_call_runs_and_the_run_answers(session: str) -> None:
    result = await _run(session, declared=True)

    assert "__interrupt__" not in result
    messages = _messages(result)
    assert [m.content for m in messages if isinstance(m, ToolMessage)] == ["created x"]
    assert messages[-1].content == "done"


@_RUNS
async def test_an_undeclared_call_is_refused_and_the_run_answers(session: str) -> None:
    result = await _run(session, declared=False)

    assert "__interrupt__" not in result
    messages = _messages(result)
    answers = [str(m.content) for m in messages if isinstance(m, ToolMessage)]
    assert len(answers) == 1
    assert "no explicit capability declaration" in answers[0]
    assert messages[-1].content == "done"
