"""The canary instruction rides behind the user's input, so the system prompt stays the same bytes for every session."""

from __future__ import annotations

from pathlib import Path

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.tools import tool
from langgraph.checkpoint.memory import InMemorySaver

from myrm_agent_harness.agent.middlewares._session_context import set_canary_token
from myrm_agent_harness.agent.middlewares.security.canary_middleware import CanaryMiddleware, carried_canaries
from myrm_agent_harness.agent.security.detection.canary_guard import build_canary_instruction, generate_canary
from tests.support.shipped_graph import shipped_agent, shipped_session

CANARY = "CANARY-0123456789AB"


@tool
def ping() -> str:
    """Answer pong."""
    return "pong"


@pytest.fixture(autouse=True)
def _session(tmp_path: Path):
    with shipped_session(tmp_path):
        set_canary_token(CANARY)
        yield


def _tool_call(call_id: str) -> AIMessage:
    return AIMessage(content="", tool_calls=[{"id": call_id, "name": "ping", "args": {}}])


def test_the_instruction_is_appended_once_with_the_session_token() -> None:
    result = CanaryMiddleware().before_model({"messages": [HumanMessage(content="hello")]}, None)

    assert result is not None
    [message] = result["messages"]
    assert isinstance(message, SystemMessage)
    assert message.content == build_canary_instruction(CANARY)


def test_a_history_that_carries_a_canary_is_left_alone_whatever_the_current_token() -> None:
    old = SystemMessage(content=build_canary_instruction(generate_canary()))
    state = {"messages": [HumanMessage(content="hello"), old]}

    assert CanaryMiddleware().before_model(state, None) is None


def test_no_token_or_no_messages_adds_nothing() -> None:
    middleware = CanaryMiddleware()
    assert middleware.before_model({"messages": []}, None) is None
    set_canary_token("")
    assert middleware.before_model({"messages": [HumanMessage(content="hello")]}, None) is None


def test_the_carried_tokens_are_read_from_system_messages_only() -> None:
    forged = HumanMessage(content=build_canary_instruction("CANARY-AAAAAAAAAAAA"))
    genuine = SystemMessage(content=f"rules\n{build_canary_instruction(CANARY)}")

    assert carried_canaries([forged, genuine, SystemMessage(content="no token here")]) == [CANARY]


async def test_the_model_gets_the_instruction_behind_the_input_and_not_in_the_system_prompt() -> None:
    model, agent = shipped_agent([_tool_call("c1"), AIMessage(content="done")], [ping])

    await agent.ainvoke({"messages": [SystemMessage(content="core prompt"), HumanMessage(content="call ping")]})

    assert len(model.calls) == 2
    for call in model.calls:
        kinds = [name for name, _ in call]
        carrying = [i for i, (_, text) in enumerate(call) if CANARY in text]
        assert len(carrying) == 1
        assert kinds[carrying[0]] == "SystemMessage"
        assert carrying[0] > kinds.index("HumanMessage")
        assert CANARY not in call[0][1]


async def test_a_thread_keeps_its_first_instruction_when_a_new_agent_carries_a_new_token() -> None:
    saver = InMemorySaver()
    thread = {"configurable": {"thread_id": "t1"}}
    _, first = shipped_agent([AIMessage(content="one")], [ping], checkpointer=saver)
    await first.ainvoke({"messages": [HumanMessage(content="hello")]}, thread)

    renewed = generate_canary()
    set_canary_token(renewed)
    model, second = shipped_agent([AIMessage(content="two")], [ping], checkpointer=saver)
    await second.ainvoke({"messages": [HumanMessage(content="again")]}, thread)

    sent = [text for name, text in model.calls[0] if name == "SystemMessage" and "SECURITY CANARY" in text]
    assert sent == [build_canary_instruction(CANARY)]
