"""The LangGraph contract the router's superseded-approval notice relies on.

A thread suspended at an approval is taken over by any new input on it: the suspended step is not resumed, and an
answer that arrives afterwards changes nothing. ``AgentRouter._retire_open_approval`` tells the chat exactly that, so
this pins it on the installed LangGraph rather than leaving it as a remembered observation.
"""

from __future__ import annotations

import operator
from typing import Annotated, TypedDict

import pytest
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command, interrupt

_CONFIG: RunnableConfig = {"configurable": {"thread_id": "t1"}}


class _State(TypedDict):
    text: str
    sent: Annotated[list[str], operator.add]


def _send_after_approval(state: _State) -> dict[str, list[str]]:
    if state["text"] != "send it":
        return {"sent": []}
    return {"sent": ["mail"] if interrupt("approve the mail?") == "approve" else []}


def _agent_suspended_at_the_approval() -> CompiledStateGraph[_State, None, _State, _State]:
    graph = StateGraph(_State)
    graph.add_node("act", _send_after_approval)
    graph.add_edge(START, "act")
    graph.add_edge("act", END)
    return graph.compile(checkpointer=InMemorySaver())


@pytest.mark.asyncio
async def test_an_approval_answered_while_suspended_runs_the_step() -> None:
    agent = _agent_suspended_at_the_approval()
    await agent.ainvoke({"text": "send it", "sent": []}, _CONFIG)
    assert (await agent.aget_state(_CONFIG)).interrupts

    final = await agent.ainvoke(Command(resume="approve"), _CONFIG)

    assert final["sent"] == ["mail"]


@pytest.mark.asyncio
async def test_new_input_ends_the_suspended_run_and_a_late_answer_changes_nothing() -> None:
    agent = _agent_suspended_at_the_approval()
    await agent.ainvoke({"text": "send it", "sent": []}, _CONFIG)

    await agent.ainvoke({"text": "hello", "sent": []}, _CONFIG)
    state = await agent.aget_state(_CONFIG)
    assert not state.interrupts
    assert not state.next

    late = await agent.ainvoke(Command(resume="approve"), _CONFIG)

    assert late["sent"] == []
    assert (await agent.aget_state(_CONFIG)).values["sent"] == []
