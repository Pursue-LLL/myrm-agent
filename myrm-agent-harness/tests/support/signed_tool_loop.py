"""Three turns of the shipped agent in a tool loop, against a provider that checks the reasoning it signed.

[INPUT]
- tests.support.enforcing_anthropic::EnforcingAnthropic (POS: a Messages API double that refuses a replay the API would refuse)
- tests.support.shipped_graph::shipped_session (POS: the session context of a run that may use tools without asking)
- agent._internals._agent_build::build_middlewares, create_registry (POS: the middleware stack an agent runs)

[OUTPUT]
- TURNS, ROUNDS, PER_TURN: how many turns the session runs, tool rounds per turn, and requests a turn makes
- signed_loop_session: the session context the loop runs in, with its tool declared safe to run unasked
- run_signed_loop: the turns themselves, through the chat model, transport, adapter, context pipeline and middleware stack

[POS]
A signed reasoning block is valid only under the exact prompt it was written in, so a test of what a middleware does
to the request of a run has to run the whole stack against a provider that enforces that. What such a test counts is
what a provider would have refused.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from langchain.agents import create_agent
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import HumanMessage
from langchain_core.tools import tool
from langgraph.checkpoint.memory import InMemorySaver

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


async def run_signed_loop(
    double: EnforcingAnthropic,
    *,
    streaming: bool = True,
    extra: Sequence[AgentMiddleware] = (),
    prompt: str = "Turn {turn}: investigate the repository and report.",
) -> None:
    """``TURNS`` runs of one chat, each ending in a closing answer after ``ROUNDS`` tool rounds of the double.

    ``extra`` are the middlewares a server adds to the stack, ``prompt`` is what the user says each turn.
    """
    llm = create_chat_model(
        "anthropic/claude-sonnet-5-5",
        base_url="http://anthropic.test",
        api_key="sk-test",
        streaming=streaming,
        max_tokens=1024,
        reasoning_effort="medium",
    )
    pipeline = create_context_pipeline_middleware(llm, enable_active_tool_prune=True, compress_batch_rounds=5)
    agent = create_agent(
        llm,
        tools=[read_file],
        middleware=build_middlewares(create_registry(), [pipeline, *extra], None),
        checkpointer=InMemorySaver(),
        system_prompt="You are a careful coding agent.",
        context_schema=dict,
    )
    with double.serving():
        for turn in range(1, TURNS + 1):
            # A run resets the completion guard's state for its turn when it starts.
            reset_completion_guard()
            await agent.ainvoke(
                {"messages": [HumanMessage(content=prompt.format(turn=turn))]},
                {"configurable": {"thread_id": "t"}, "recursion_limit": 400},
                context={"chat_id": "chat", "max_context_tokens": _WINDOW},
            )
