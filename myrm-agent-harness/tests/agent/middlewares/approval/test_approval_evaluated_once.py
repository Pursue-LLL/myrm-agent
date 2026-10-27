"""A tool batch is judged once, however long the user takes to answer the approval card.

LangGraph resumes an interrupted node by running it again from its first line. Everything the approval node did
before ``interrupt()`` therefore ran twice: the security reviewer was asked again, the refusal counters moved again,
and a verdict that changed in between could drop the very decision the user had just made. These tests drive the
shipped middleware stack through a real pause and resume.
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
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command

from myrm_agent_harness.agent._internals._agent_build import build_middlewares, create_registry
from myrm_agent_harness.agent.middlewares._session_context import set_security_config, set_workspace_root
from myrm_agent_harness.agent.middlewares.approval import set_approval_session
from myrm_agent_harness.agent.middlewares.approval._batch_review import register_security_reviewer
from myrm_agent_harness.agent.middlewares.approval.evaluation import APPROVAL_EVALUATION_KEY
from myrm_agent_harness.agent.middlewares.approval.helpers import clear_all_session_denials_for_tests
from myrm_agent_harness.agent.security.types import (
    PrivacyPolicy,
    RecentToolCall,
    ReviewDecision,
    ReviewResult,
    SecurityConfig,
)
from myrm_agent_harness.runtime.checkpointing.factory import create_checkpointer

RAN: list[str] = []
COMMAND = "python3 setup.py install"


@tool
def bash_code_execute_tool(command: str) -> str:
    """Record that the command ran."""
    RAN.append(command)
    return "done"


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


class SequencedReviewer:
    """Gives its verdicts in order and repeats the last one, counting how often it was asked and what it was shown."""

    def __init__(self, *verdicts: ReviewDecision) -> None:
        self.verdicts = verdicts
        self.asked = 0
        self.shown: list[tuple[RecentToolCall, ...]] = []

    async def review(
        self,
        command: str,
        *,
        workspace_root: str | None = None,
        intent_context: str | None = None,
        taint_labels: frozenset[str] | None = None,
        recent_tool_calls: tuple[RecentToolCall, ...] = (),
        model_id: str | None = None,
        trusted_domains: tuple[str, ...] = (),
    ) -> ReviewResult:
        verdict = self.verdicts[min(self.asked, len(self.verdicts) - 1)]
        self.asked += 1
        self.shown.append(recent_tool_calls)
        return ReviewResult(decision=verdict, reason="scripted verdict")


CALL_THE_COMMAND = AIMessage(
    content="", tool_calls=[{"id": "c1", "name": "bash_code_execute_tool", "args": {"command": COMMAND}}]
)


def _agent(
    script: list[AIMessage] | None = None, checkpointer: BaseCheckpointSaver[str] | None = None
) -> CompiledStateGraph:
    return create_agent(
        ScriptedModel(script=script or [CALL_THE_COMMAND, AIMessage(content="done")]),
        tools=[bash_code_execute_tool],
        middleware=build_middlewares(create_registry(), []),
        checkpointer=checkpointer or InMemorySaver(),
    )


@pytest.fixture(autouse=True)
def _session(tmp_path: Path) -> Iterator[None]:
    RAN.clear()
    clear_all_session_denials_for_tests()
    set_security_config(SecurityConfig(yolo_mode_enabled=False, privacy_policy=PrivacyPolicy(enabled=False)))
    set_workspace_root(str(tmp_path))
    set_approval_session("evaluated-once")
    yield
    register_security_reviewer(None)
    set_security_config(None)
    set_workspace_root("")
    set_approval_session("")
    clear_all_session_denials_for_tests()


async def _ask_then_answer(agent: CompiledStateGraph, decision: dict[str, str]) -> dict[str, object]:
    config = {"configurable": {"thread_id": "t"}}
    paused = await agent.ainvoke({"messages": [HumanMessage(content="install")]}, config)
    assert paused["__interrupt__"], "the batch should wait for the user"
    return await agent.ainvoke(Command(resume={"decisions": [decision]}), config)


async def test_the_reviewer_is_asked_once_for_a_batch_that_waits_for_the_user() -> None:
    reviewer = SequencedReviewer(ReviewDecision.UNCERTAIN)
    register_security_reviewer(reviewer)

    await _ask_then_answer(_agent(), {"type": "approve"})

    assert reviewer.asked == 1
    assert RAN == [COMMAND]


async def test_a_verdict_that_turns_to_allow_while_the_card_is_open_does_not_undo_the_users_refusal() -> None:
    register_security_reviewer(SequencedReviewer(ReviewDecision.UNCERTAIN, ReviewDecision.ALLOW))

    result = await _ask_then_answer(_agent(), {"type": "reject", "feedback": "not now"})

    assert RAN == []
    answers = [m for m in result["messages"] if isinstance(m, ToolMessage)]
    assert [m.status for m in answers] == ["error"]


async def test_a_verdict_that_turns_to_deny_while_the_card_is_open_does_not_overrule_the_users_approval() -> None:
    register_security_reviewer(SequencedReviewer(ReviewDecision.UNCERTAIN, ReviewDecision.DENY))

    result = await _ask_then_answer(_agent(), {"type": "approve"})

    assert RAN == [COMMAND]
    answers = [m for m in result["messages"] if isinstance(m, ToolMessage)]
    assert [m.status for m in answers] == ["success"]


async def test_a_refusal_the_user_gives_is_answered_once_and_the_command_never_runs() -> None:
    register_security_reviewer(SequencedReviewer(ReviewDecision.UNCERTAIN))

    result = await _ask_then_answer(_agent(), {"type": "reject", "feedback": "not now"})

    assert RAN == []
    answers = [m for m in result["messages"] if isinstance(m, ToolMessage)]
    assert [m.tool_call_id for m in answers] == ["c1"]
    assert answers[0].status == "error"


async def test_the_batch_is_still_judged_once_when_the_process_restarts_while_the_card_is_open(tmp_path: Path) -> None:
    reviewer = SequencedReviewer(ReviewDecision.UNCERTAIN, ReviewDecision.ALLOW)
    register_security_reviewer(reviewer)
    config = {"configurable": {"thread_id": "t"}}
    database = str(tmp_path / "checkpoints.db")

    saver, close = await create_checkpointer("sqlite", database)
    try:
        paused = await _agent(checkpointer=saver).ainvoke({"messages": [HumanMessage(content="install")]}, config)
        assert paused["__interrupt__"]
    finally:
        await close()

    saver, close = await create_checkpointer("sqlite", database)
    try:
        resumed = _agent(script=[AIMessage(content="done")], checkpointer=saver)
        result = await resumed.ainvoke(Command(resume={"decisions": [{"type": "reject", "feedback": "no"}]}), config)
    finally:
        await close()

    assert reviewer.asked == 1
    assert RAN == []
    assert [m.status for m in result["messages"] if isinstance(m, ToolMessage)] == ["error"]


async def test_the_stored_verdicts_are_kept_for_the_pause_and_gone_once_the_batch_is_settled() -> None:
    register_security_reviewer(SequencedReviewer(ReviewDecision.UNCERTAIN))
    agent = _agent()
    config = {"configurable": {"thread_id": "t"}}

    paused = await agent.ainvoke({"messages": [HumanMessage(content="install")]}, config)

    assert APPROVAL_EVALUATION_KEY not in paused
    kept = (await agent.aget_state(config)).values[APPROVAL_EVALUATION_KEY]
    assert [entry["tool_call"]["id"] for entry in kept["pending"]] == ["c1"]

    settled = await agent.ainvoke(Command(resume={"decisions": [{"type": "approve"}]}), config)

    assert APPROVAL_EVALUATION_KEY not in settled
    assert (await agent.aget_state(config)).values.get(APPROVAL_EVALUATION_KEY) is None


NEXT_COMMAND = "python3 setup.py build"
CALL_THE_NEXT_COMMAND = AIMessage(
    content="", tool_calls=[{"id": "c2", "name": "bash_code_execute_tool", "args": {"command": NEXT_COMMAND}}]
)


async def _second_review_after(first_decision: dict[str, str]) -> SequencedReviewer:
    """Answer the first card, let the model ask for a second command, and return the reviewer once it is asked again."""
    reviewer = SequencedReviewer(ReviewDecision.UNCERTAIN)
    register_security_reviewer(reviewer)
    agent = _agent(script=[CALL_THE_COMMAND, CALL_THE_NEXT_COMMAND, AIMessage(content="done")])
    config = {"configurable": {"thread_id": "t"}}

    await agent.ainvoke({"messages": [HumanMessage(content="install")]}, config)
    second_card = await agent.ainvoke(Command(resume={"decisions": [first_decision]}), config)

    assert second_card["__interrupt__"], "the second command should wait for the user too"
    assert reviewer.asked == 2
    return reviewer


def _commands(shown: tuple[RecentToolCall, ...]) -> list[object]:
    return [call.args["command"] for call in shown]


async def test_a_call_the_user_refused_is_not_shown_to_the_reviewer_as_a_recent_action() -> None:
    reviewer = await _second_review_after({"type": "reject", "feedback": "not now"})

    assert RAN == []
    assert _commands(reviewer.shown[1]) == [NEXT_COMMAND]


async def test_a_call_that_ran_is_shown_to_the_reviewer_as_a_recent_action() -> None:
    reviewer = await _second_review_after({"type": "approve"})

    assert RAN == [COMMAND]
    assert _commands(reviewer.shown[1]) == [COMMAND, NEXT_COMMAND]
