"""Turns of the shipped agent in a tool loop, against a provider that checks the reasoning it signed.

[INPUT]
- tests.support.enforcing_anthropic::EnforcingAnthropic (POS: a Messages API double that refuses a replay the API would refuse)
- tests.support.shipped_graph::shipped_session (POS: the session context of a run that may use tools without asking)
- agent._internals._agent_build::build_middlewares, create_registry (POS: the middleware stack an agent runs)

[OUTPUT]
- TURNS, ROUNDS, PER_TURN: how many turns the session runs, tool rounds per turn, and requests a turn makes
- signed_loop_session: the session context the loop runs in, with its tool declared safe to run unasked
- signed_agent: the shipped agent over the chat model, transport, adapter, context pipeline and middleware stack
- run_signed_loop: the turns themselves, run on that agent

[POS]
A signed reasoning block is valid only under the exact prompt it was written in, so a test of what a middleware does
to the request of a run has to run the whole stack against a provider that enforces that. What such a test counts is
what a provider would have refused.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from langchain.agents import create_agent
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import HumanMessage
from langchain_core.tools import BaseTool, tool
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph.state import CompiledStateGraph

from myrm_agent_harness.agent._internals._agent_build import build_middlewares, create_registry
from myrm_agent_harness.agent.middlewares.completion.completion_guard import reset_completion_guard
from myrm_agent_harness.agent.middlewares.context_pipeline.context_pipeline_middleware import (
    create_context_pipeline_middleware,
)
from myrm_agent_harness.agent.security.tool_registry import TOOL_SAFETY_METADATA, SafetyMetadata
from myrm_agent_harness.toolkits.llms.core.llm import create_chat_model
from tests.support.enforcing_anthropic import EnforcingAnthropic
from tests.support.shipped_graph import shipped_session

TURNS = 3
ROUNDS = 6
PER_TURN = ROUNDS + 1
_WINDOW = 200_000
_OUTPUT = ("line of tool output with distinct words alpha beta gamma delta epsilon zeta eta theta. " * 100)[:8000]


@tool
async def read_file(path: str) -> str:
    """Read a file."""
    return f"{path}\n{_OUTPUT}"


@contextmanager
def signed_loop_session(workspace: Path) -> Iterator[None]:
    """The session context of the loop's runs in *workspace*; the registry of tool safety is restored on exit."""
    declared = {"read_file": SafetyMetadata(is_read_only=True, is_concurrent_safe=True)}
    with patch.dict(TOOL_SAFETY_METADATA, declared), shipped_session(workspace):
        yield


def signed_agent(
    *,
    streaming: bool = True,
    extra: Sequence[AgentMiddleware] = (),
    tools: Sequence[BaseTool] = (read_file,),
    reasoning_effort: str | None = "medium",
) -> CompiledStateGraph:
    """The shipped agent over a Claude route.

    ``extra`` are the middlewares a server adds to the stack. ``tools`` stand in for ``read_file``, so each must be
    named ``read_file``: that is the call the double makes and the tool the session declares safe to run unasked.
    Without a ``reasoning_effort`` the route signs nothing.
    """
    llm = create_chat_model(
        "anthropic/claude-sonnet-5-5",
        base_url="http://anthropic.test",
        api_key="sk-test",
        streaming=streaming,
        max_tokens=1024,
        reasoning_effort=reasoning_effort,
    )
    pipeline = create_context_pipeline_middleware(llm, enable_active_tool_prune=True, compress_batch_rounds=5)
    return create_agent(
        llm,
        tools=list(tools),
        middleware=build_middlewares(create_registry(), [pipeline, *extra], None),
        checkpointer=InMemorySaver(),
        system_prompt="You are a careful coding agent.",
        context_schema=dict,
    )


async def run_signed_loop(
    double: EnforcingAnthropic,
    *,
    streaming: bool = True,
    extra: Sequence[AgentMiddleware] = (),
    prompt: str = "Turn {turn}: investigate the repository and report.",
    tools: Sequence[BaseTool] = (read_file,),
    reasoning_effort: str | None = "medium",
    turns: int = TURNS,
    window: int = _WINDOW,
    before_turn: Callable[[int], None] | None = None,
) -> None:
    """``turns`` runs of one chat, each ending in a closing answer after the double's tool rounds.

    ``prompt`` is what the user says each turn, ``window`` the context window of the model and ``before_turn`` what
    happens between the end of one run and the start of the next (given the number of the turn about to start).
    """
    agent = signed_agent(streaming=streaming, extra=extra, tools=tools, reasoning_effort=reasoning_effort)
    with double.serving():
        for turn in range(1, turns + 1):
            # A run resets the completion guard's state for its turn when it starts.
            reset_completion_guard()
            if before_turn is not None:
                before_turn(turn)
            await agent.ainvoke(
                {"messages": [HumanMessage(content=prompt.format(turn=turn))]},
                {"configurable": {"thread_id": "t"}, "recursion_limit": 400},
                context={"chat_id": "chat", "max_context_tokens": window},
            )
