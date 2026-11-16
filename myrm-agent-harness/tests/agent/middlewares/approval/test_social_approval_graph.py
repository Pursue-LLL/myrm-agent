"""A person's approval of a call that cannot be taken back runs it, through the real graph.

With the shipped middleware stack on a real LangGraph agent, the call pauses the run and the approval resumes it:
1. A socially irreversible call (a git push, a channel notice, a publish) runs when the person approves it. Its card
   carries no digest for the client to echo, so the approval needs none.
2. A payment is held to a stronger check: its card carries a digest, and an approval that does not echo it is refused.
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
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command

import myrm_agent_harness.agent.security.approval_flow as approval_flow
from myrm_agent_harness.agent._internals._agent_build import build_middlewares, create_registry
from myrm_agent_harness.agent.middlewares._session_context import (
    set_approval_session,
    set_approval_user_id,
    set_security_config,
    set_workspace_root,
)
from myrm_agent_harness.agent.middlewares.approval import get_approval_rate_limiter
from myrm_agent_harness.agent.middlewares.approval.batch_processor import register_security_reviewer
from myrm_agent_harness.agent.middlewares.approval.helpers import clear_all_session_denials_for_tests
from myrm_agent_harness.agent.security.audit import reset_audit_log
from myrm_agent_harness.agent.security.guards.taint_tracker import reset_taint_tracker
from myrm_agent_harness.agent.security.types import PrivacyPolicy, SecurityConfig

_executed: list[str] = []

_SOCIAL_CALLS = pytest.mark.parametrize(
    ("tool_name", "args", "ran"),
    [
        pytest.param(
            "bash_code_execute_tool", {"command": "git push origin main"}, "run:git push origin main", id="git-push"
        ),
        pytest.param("channel_notify_tool", {"message": "hello"}, "notify:hello", id="channel-notice"),
        pytest.param("artifact_publish", {"path": "report.md"}, "publish:report.md", id="artifact-publish"),
    ],
)


@tool
def bash_code_execute_tool(command: str) -> str:
    """Run a shell command."""
    _executed.append(f"run:{command}")
    return "ran"


@tool
def channel_notify_tool(message: str) -> str:
    """Notify a channel."""
    _executed.append(f"notify:{message}")
    return "sent"


@tool
def artifact_publish(path: str) -> str:
    """Publish an artifact."""
    _executed.append(f"publish:{path}")
    return "published"


@tool
def mcp__stripe__create_payment_intent(amount: int, currency: str) -> str:
    """Create a payment."""
    _executed.append(f"pay:{amount}{currency}")
    return "paid"


class CallsOnce(BaseChatModel):
    """Makes one tool call in its first turn, then answers."""

    tool_name: str
    tool_args: dict[str, object]
    served: int = 0

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def bind_tools(self, tools: object, **kwargs: object) -> CallsOnce:
        return self

    def _generate(
        self, messages: list[BaseMessage], stop: list[str] | None = None, run_manager: object = None, **kwargs: object
    ) -> ChatResult:
        if self.served == 0:
            reply = AIMessage(content="", tool_calls=[{"id": "c0", "name": self.tool_name, "args": self.tool_args}])
        else:
            reply = AIMessage(content="done")
        self.served += 1
        return ChatResult(generations=[ChatGeneration(message=reply)])


@pytest.fixture(autouse=True)
def _web_session(tmp_path: Path) -> Iterator[None]:
    approval_flow._allowlist = approval_flow.Allowlist()
    reset_taint_tracker()
    reset_audit_log()
    clear_all_session_denials_for_tests()
    get_approval_rate_limiter().reset(None)
    register_security_reviewer(None)
    _executed.clear()
    set_security_config(SecurityConfig(yolo_mode_enabled=False, privacy_policy=PrivacyPolicy(enabled=False)))
    set_workspace_root(str(tmp_path))
    set_approval_session("web-session")
    set_approval_user_id("user-1")
    yield
    register_security_reviewer(None)
    reset_taint_tracker()


def _agent(tool_name: str, args: dict[str, object]) -> CompiledStateGraph:
    return create_agent(
        CallsOnce(tool_name=tool_name, tool_args=args),
        tools=[bash_code_execute_tool, channel_notify_tool, artifact_publish, mcp__stripe__create_payment_intent],
        middleware=build_middlewares(create_registry(), []),
        checkpointer=InMemorySaver(),
    )


async def _pause(agent: CompiledStateGraph) -> dict[str, object]:
    """Run to the approval card; the card is the review config of the one pending call."""
    paused = await agent.ainvoke({"messages": [HumanMessage(content="go")]}, {"configurable": {"thread_id": "t"}})
    assert "__interrupt__" in paused
    card = paused["__interrupt__"][0].value["reviewConfigs"][0]
    assert isinstance(card, dict)
    return card


async def _approve(agent: CompiledStateGraph, decision: dict[str, object]) -> list[BaseMessage]:
    final = await agent.ainvoke(Command(resume={"decisions": [decision]}), {"configurable": {"thread_id": "t"}})
    messages = final["messages"]
    assert isinstance(messages, list)
    return messages


@_SOCIAL_CALLS
async def test_approving_a_social_call_runs_it(tool_name: str, args: dict[str, object], ran: str) -> None:
    agent = _agent(tool_name, args)

    card = await _pause(agent)
    messages = await _approve(agent, {"type": "approve"})

    assert card["sociallyIrreversible"] is True
    assert "actionDigest" not in card
    assert _executed == [ran]
    assert not [m for m in messages if isinstance(m, ToolMessage) and m.status == "error"]
    assert messages[-1].content == "done"


async def test_a_payment_card_carries_the_digest_its_approval_must_echo() -> None:
    agent = _agent("mcp__stripe__create_payment_intent", {"amount": 1999, "currency": "usd"})

    card = await _pause(agent)
    messages = await _approve(agent, {"type": "approve", "actionDigest": card["actionDigest"]})

    assert _executed == ["pay:1999usd"]
    assert not [m for m in messages if isinstance(m, ToolMessage) and m.status == "error"]


async def test_a_payment_approved_without_the_digest_is_refused() -> None:
    agent = _agent("mcp__stripe__create_payment_intent", {"amount": 1999, "currency": "usd"})

    await _pause(agent)
    messages = await _approve(agent, {"type": "approve"})

    refusals = [str(m.content) for m in messages if isinstance(m, ToolMessage) and m.status == "error"]
    assert _executed == []
    assert len(refusals) == 1
    assert "digest verification failed" in refusals[0]
