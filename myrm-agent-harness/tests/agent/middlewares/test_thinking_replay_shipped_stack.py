"""Signed reasoning through the shipped stack: a tool loop is replayed whole, and a refusal costs one retry.

A reasoning block the provider signed is valid only under the exact prompt it was written in, and the provider checks
it on every request. These tests run the real chat model, transport, adapter, context pipeline and middleware stack
against a provider double that enforces those checks, so what they count is what a provider would have refused.

[INPUT]
- tests.support.enforcing_anthropic::EnforcingAnthropic (POS: a Messages API double that refuses a replay the API would refuse)
- tests.support.signed_tool_loop::run_signed_loop, signed_loop_session (POS: three turns of the shipped agent in a tool loop against that double)

[POS]
Graph-level guard of the signed-reasoning replay: capture on the stream and the non-stream path, replay inside the
tool loop, pruning at the turn boundary and the retry net.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterator
from pathlib import Path

import pytest
from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain_core.messages import HumanMessage

from tests.support.enforcing_anthropic import EnforcingAnthropic
from tests.support.signed_tool_loop import PER_TURN, ROUNDS, TURNS, run_signed_loop, signed_loop_session


@pytest.fixture(autouse=True)
def _session(tmp_path: Path) -> Iterator[None]:
    with signed_loop_session(tmp_path):
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


@pytest.mark.asyncio
@pytest.mark.parametrize("streaming", [True, False], ids=["stream", "non-stream"])
async def test_a_tool_loop_replays_every_block_of_the_loop_and_none_of_an_earlier_turn(streaming: bool) -> None:
    double = EnforcingAnthropic(tool_rounds=ROUNDS)

    await run_signed_loop(double, streaming=streaming)

    assert len(double.requests) == TURNS * PER_TURN
    assert double.refused == []
    assert all(record.thinking for record in double.accepted)
    # Request k of a turn sends back the k blocks the turn's earlier rounds produced; the next turn starts clean.
    assert [record.replayed for record in double.accepted] == list(range(PER_TURN)) * TURNS


@pytest.mark.asyncio
async def test_a_refused_replay_is_retried_once_and_that_run_goes_on_without_reasoning() -> None:
    double = EnforcingAnthropic(tool_rounds=ROUNDS)

    await run_signed_loop(double, extra=[_EditOneRequest(at_call=4)])

    assert [record.reason for record in double.refused] == ["the prompt before the block changed"]
    assert len(double.requests) == TURNS * PER_TURN + 1
    first_turn = double.accepted[:PER_TURN]
    # The refused fourth request is sent again bare; the rest of the run asks for no reasoning, the next runs do.
    assert [record.thinking for record in first_turn] == [True, True, True] + [False] * (PER_TURN - 3)
    assert all(record.thinking for record in double.accepted[PER_TURN:])
