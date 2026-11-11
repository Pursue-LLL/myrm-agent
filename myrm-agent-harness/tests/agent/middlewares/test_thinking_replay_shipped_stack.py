"""Signed reasoning through the shipped stack: a tool loop is replayed whole, and a refusal costs one retry.

A reasoning block the provider signed is valid only under the exact prompt it was written in, and the provider checks
it on every request. These tests run the real chat model, transport, adapter, context pipeline and middleware stack
against a provider double that enforces those checks, so what they count is what a provider would have refused.

[INPUT]
- tests.support.enforcing_anthropic::EnforcingAnthropic (POS: a Messages API double that refuses a replay the API would refuse)
- tests.support.shipped_graph::shipped_session (POS: the session context of a run that may use tools without asking)
- agent._internals._agent_build::build_middlewares, create_registry (POS: the middleware stack an agent runs)

[POS]
Graph-level guard of the signed-reasoning replay: capture on the stream and the non-stream path, replay inside the
tool loop, pruning at the turn boundary and the retry net.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterator, Sequence
from pathlib import Path

import pytest
from langchain.agents import create_agent
from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain_core.messages import HumanMessage
from langchain_core.tools import tool
from langgraph.checkpoint.memory import InMemorySaver

from myrm_agent_harness.agent._internals._agent_build import build_middlewares, create_registry
from myrm_agent_harness.agent.middlewares.context_pipeline.context_pipeline_middleware import (
    create_context_pipeline_middleware,
)
from myrm_agent_harness.agent.security.tool_registry import TOOL_SAFETY_METADATA, SafetyMetadata
from myrm_agent_harness.toolkits.llms.core.llm import create_chat_model
from tests.support.enforcing_anthropic import EnforcingAnthropic
from tests.support.shipped_graph import shipped_session

_TURNS = 3
_ROUNDS = 6
_WINDOW = 200_000
_OUTPUT = ("line of tool output with distinct words alpha beta gamma delta epsilon zeta eta theta. " * 100)[:8000]


@tool
async def read_file(path: str) -> str:
    """Read a file."""
    return f"{path}\n{_OUTPUT}"


@pytest.fixture(autouse=True)
def _session(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setitem(TOOL_SAFETY_METADATA, "read_file", SafetyMetadata(is_read_only=True, is_concurrent_safe=True))
    with shipped_session(tmp_path):
        yield


class _EditOneRequest(AgentMiddleware):
    """Rewrites the user's first message in one request, the way a stage of the stack that edits history would."""

    def __init__(self, *, at_call: int) -> None:
        super().__init__()
        self._at_call = at_call
        self._calls = 0

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        self._calls += 1
        if self._calls == self._at_call:
            edited = HumanMessage(content=f"{request.messages[0].content} (edited)")
            request = request.override(messages=[edited, *request.messages[1:]])
        return await handler(request)


async def _run_session(double: EnforcingAnthropic, *, streaming: bool, extra: Sequence[AgentMiddleware] = ()) -> None:
    llm = create_chat_model(
        "anthropic/claude-sonnet-5-5",
        base_url="http://anthropic.test",
        api_key="sk-test",
        streaming=streaming,
        max_tokens=1024,
        reasoning_effort="medium",
    )
    pipeline = create_context_pipeline_middleware(llm, enable_active_tool_prune=True, compress_batch_rounds=5)
    middlewares = build_middlewares(create_registry(), [pipeline, *extra], None)
    agent = create_agent(
        llm,
        tools=[read_file],
        middleware=middlewares,
        checkpointer=InMemorySaver(),
        system_prompt="You are a careful coding agent.",
        context_schema=dict,
    )
    with double.serving():
        for turn in range(1, _TURNS + 1):
            await agent.ainvoke(
                {"messages": [HumanMessage(content=f"Turn {turn}: investigate the repository and report.")]},
                {"configurable": {"thread_id": "t"}, "recursion_limit": 400},
                context={"chat_id": "chat", "max_context_tokens": _WINDOW},
            )


@pytest.mark.asyncio
@pytest.mark.parametrize("streaming", [True, False], ids=["stream", "non-stream"])
async def test_a_tool_loop_replays_every_block_of_the_loop_and_none_of_an_earlier_turn(streaming: bool) -> None:
    double = EnforcingAnthropic(tool_rounds=_ROUNDS)

    await _run_session(double, streaming=streaming)

    per_turn = _ROUNDS + 1
    assert len(double.requests) == _TURNS * per_turn
    assert double.refused == []
    assert all(record.thinking for record in double.accepted)
    # Request k of a turn sends back the k blocks the turn's earlier rounds produced; the next turn starts clean.
    assert [record.replayed for record in double.accepted] == list(range(per_turn)) * _TURNS


@pytest.mark.asyncio
async def test_a_refused_replay_is_retried_once_and_that_run_goes_on_without_reasoning() -> None:
    double = EnforcingAnthropic(tool_rounds=_ROUNDS)

    await _run_session(double, streaming=True, extra=[_EditOneRequest(at_call=4)])

    per_turn = _ROUNDS + 1
    assert [record.reason for record in double.refused] == ["the prompt before the block changed"]
    assert len(double.requests) == _TURNS * per_turn + 1
    first_turn = double.accepted[:per_turn]
    # The refused fourth request is sent again bare; the rest of the run asks for no reasoning, the next runs do.
    assert [record.thinking for record in first_turn] == [True, True, True] + [False] * (per_turn - 3)
    assert all(record.thinking for record in double.accepted[per_turn:])
