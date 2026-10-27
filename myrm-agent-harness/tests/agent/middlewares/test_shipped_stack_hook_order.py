"""The order in which the shipped middleware chain meets a model response.

LangChain runs the ``after_model`` hooks from the last middleware to the first. The completion guard and the
clarification guard hold back or strip tool calls, so both must run before tool approval: the user is never asked
to approve a call that is not going to run. The calls are judged in a node of their own, right before the node that
asks the user, because resuming an approval pause runs the asking node again from its first line.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from langchain.agents import create_agent
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import tool
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph.state import CompiledStateGraph

from myrm_agent_harness.agent._internals._agent_build import build_middlewares, create_registry
from myrm_agent_harness.agent.middlewares._session_context import set_security_config, set_workspace_root
from myrm_agent_harness.agent.security.types import PrivacyPolicy, SecurityConfig

RAN: list[str] = []


@tool
def step() -> str:
    """Record that the step ran."""
    RAN.append("step")
    return "done"


@tool
def ask_question_tool(questions: str) -> str:
    """Answer for the user."""
    return "asked"


class ScriptedModel(BaseChatModel):
    """Answers from a script, one reply per call."""

    script: list[AIMessage]
    served: int = 0

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def bind_tools(self, tools: object, **kwargs: object) -> ScriptedModel:
        return self

    def _generate(
        self, messages: list[BaseMessage], stop: list[str] | None = None, run_manager: object = None, **kwargs: object
    ) -> ChatResult:
        reply = self.script[min(self.served, len(self.script) - 1)]
        self.served += 1
        return ChatResult(generations=[ChatGeneration(message=reply)])


def _shipped_agent(script: list[AIMessage]) -> CompiledStateGraph:
    return create_agent(
        ScriptedModel(script=script),
        tools=[step, ask_question_tool],
        middleware=build_middlewares(create_registry(), []),
        checkpointer=InMemorySaver(),
    )


@pytest.fixture(autouse=True)
def _session(tmp_path: Path) -> Iterator[None]:
    RAN.clear()
    set_security_config(SecurityConfig(yolo_mode_enabled=False, privacy_policy=PrivacyPolicy(enabled=False)))
    set_workspace_root(str(tmp_path))
    yield
    set_security_config(None)
    set_workspace_root("")


def test_a_model_response_meets_the_guards_then_the_evaluation_then_the_approval_that_asks_the_user() -> None:
    edges = {(edge.source, edge.target) for edge in _shipped_agent([AIMessage(content="ok")]).get_graph().edges}

    assert ("CompletionGuard.after_model", "ClarificationGuardMiddleware.after_model") in edges
    assert ("ClarificationGuardMiddleware.after_model", "ApprovalEvaluationMiddleware.after_model") in edges
    assert ("ApprovalEvaluationMiddleware.after_model", "ToolApprovalMiddleware.after_model") in edges


async def test_a_tool_the_clarification_guard_strips_is_never_put_to_the_user_for_approval() -> None:
    calls = [
        {"id": "q1", "name": "ask_question_tool", "args": {"questions": "which?"}},
        {"id": "s1", "name": "step", "args": {}},
    ]
    agent = _shipped_agent([AIMessage(content="", tool_calls=calls), AIMessage(content="done")])

    result = await agent.ainvoke(
        {"messages": [HumanMessage(content="ask and step")]}, {"configurable": {"thread_id": "t"}}
    )

    assert "__interrupt__" not in result
    assert RAN == []


async def test_a_tool_that_needs_approval_still_asks_the_user_when_nothing_strips_it() -> None:
    agent = _shipped_agent(
        [AIMessage(content="", tool_calls=[{"id": "s1", "name": "step", "args": {}}]), AIMessage(content="done")]
    )

    result = await agent.ainvoke({"messages": [HumanMessage(content="step")]}, {"configurable": {"thread_id": "t"}})

    assert result["__interrupt__"]
    assert RAN == []
