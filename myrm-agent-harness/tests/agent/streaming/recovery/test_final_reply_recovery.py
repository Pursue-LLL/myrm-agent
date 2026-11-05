"""A recovery judges the model's latest reply, even when that reply is empty.

``event_handlers`` leaves a reply with no content, no tool calls and no withheld calls out of
``collected_messages`` (there is nothing to re-send), so a recovery that read the last AIMessage there judged an
earlier round's reply instead: an empty reply after a tool round ended the run with no answer, and a reasoning-only
reply cut by the output limit looked like a failed tool call.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from myrm_agent_harness.toolkits.llms.ephemeral_output_tokens import reset_ephemeral_max_output_tokens
from myrm_agent_harness.toolkits.llms.errors import MyrmLLMError

from ..scripted_agent import (
    BASE_MAX_TOKENS,
    FULL_REPORT,
    TRACKER_PATH,
    complete_write,
    empty_reply,
    final_answer,
    make_context,
    make_executor,
    reasoning_only_cut,
    run_agent,
)

EMPTY_HINT = "completely empty"
THINKING_HINT = "spent its entire output budget"
TOOL_HINT = "Your previous tool call was not executed"


@pytest.fixture(autouse=True)
def _isolated_output_budget():
    reset_ephemeral_max_output_tokens()
    yield
    reset_ephemeral_max_output_tokens()


def _last_message(request) -> str:
    return request.messages[-1][1]


@pytest.mark.asyncio
@pytest.mark.parametrize("gated", [False, True], ids=["fresh", "resumed"])
async def test_empty_reply_after_a_tool_round_is_retried(gated: bool):
    run, model = await run_agent([complete_write(), empty_reply(), final_answer()], gated=gated)

    assert run.error is None
    assert run.executed == [("report.md", FULL_REPORT)]  # the retry asked for an answer, not for another write
    assert len(model.requests) == 3
    assert EMPTY_HINT in _last_message(model.requests[2])
    assert run.approvals == (1 if gated else 0)


@pytest.mark.asyncio
@pytest.mark.parametrize("gated", [False, True], ids=["fresh", "resumed"])
async def test_reasoning_only_cut_after_a_tool_round_gets_a_larger_budget_and_the_right_hint(gated: bool):
    run, model = await run_agent([complete_write(), reasoning_only_cut(), final_answer()], gated=gated)

    assert run.error is None
    assert len(model.requests) == 3
    hint = _last_message(model.requests[2])
    assert THINKING_HINT in hint
    assert TOOL_HINT not in hint
    assert model.requests[2].max_tokens > BASE_MAX_TOKENS


@pytest.mark.asyncio
async def test_first_reply_of_a_conversation_can_be_empty():
    """No assistant message precedes it, so nothing in ``collected_messages`` could stand in for the reply."""
    run, model = await run_agent([empty_reply(), final_answer()])

    assert run.error is None
    assert len(model.requests) == 2
    assert EMPTY_HINT in _last_message(model.requests[1])


@pytest.mark.asyncio
async def test_reasoning_field_reply_that_stopped_normally_is_an_empty_response():
    """A reply that only reasoned and then stopped is as empty to the user as one with nothing in it."""
    reasoned_then_stopped = (AIMessage(content="", additional_kwargs={"reasoning_content": "Thinking it over"}), "stop")

    run, model = await run_agent([complete_write(), reasoned_then_stopped, final_answer()])

    assert run.error is None
    assert len(model.requests) == 3
    hint = _last_message(model.requests[2])
    assert EMPTY_HINT in hint
    assert THINKING_HINT not in hint


@pytest.mark.asyncio
async def test_repeated_empty_replies_end_in_an_error_not_in_silence():
    run, model = await run_agent([complete_write(), empty_reply(), empty_reply(), empty_reply()])

    assert len(model.requests) == 4  # the write, the empty reply, and two retries
    assert isinstance(run.error, MyrmLLMError)
    assert "[format] LLM returned an empty response repeatedly" in str(run.error)


@pytest.mark.asyncio
async def test_safety_refusal_without_a_fallback_is_asked_again_then_reported():
    """The refusal is an empty reply; with no safety fallback to switch to it takes the empty-response path."""
    refusal = (AIMessage(content=""), "content_filter")

    run, model = await run_agent([complete_write(), refusal, refusal, refusal])

    assert len(model.requests) == 4  # the write, the refusal, and two retries
    assert isinstance(run.error, MyrmLLMError)


@pytest.mark.asyncio
async def test_reasoning_cuts_stop_where_the_budget_recovery_gives_up():
    """The truncation recovery owns a reply cut inside its reasoning; once it gives up, nothing asks again."""
    cuts = [reasoning_only_cut() for _ in range(4)]

    run, model = await run_agent([complete_write(), *cuts])

    assert run.error is None
    assert len(model.requests) == 5  # the write, the first cut, and three boosted retries
    assert run.compactor.steps.count("thinking_budget_exhausted") == 4  # three retries announced, then the give-up
    assert not any(EMPTY_HINT in _last_message(request) for request in model.requests)


class _PassesAgent:
    """Streams one prepared list of ``updates`` chunks per pass; later passes repeat the last list."""

    def __init__(self, passes: list[list[tuple[str, dict[str, dict[str, list[AIMessage]]]]]]) -> None:
        self.passes = passes
        self.calls = 0

    async def astream(self, *_args: object, **_kwargs: object):
        chunks = self.passes[min(self.calls, len(self.passes) - 1)]
        self.calls += 1
        for chunk in chunks:
            yield chunk


@pytest.mark.asyncio
async def test_a_reply_does_not_outlive_the_pass_that_produced_it():
    """A pass that delivers no reply must not re-trigger the recovery of the previous pass's reply."""
    empty = ("updates", {"model": {"messages": [AIMessage(content="")]}})
    agent = _PassesAgent([[empty], []])
    executor = make_executor(make_context(agent, {"messages": [HumanMessage(content="hi")]}))
    tracker = MagicMock(last_finish_reason="stop", usage=None, total_cost_usd=0.0)

    with (
        patch("myrm_agent_harness.agent.hooks.executor.fire_hook", new_callable=AsyncMock),
        patch(TRACKER_PATH, return_value=tracker),
    ):
        await executor.execute()

    assert agent.calls == 2  # the empty reply, then the pass its recovery started


@pytest.mark.asyncio
async def test_a_run_that_produced_no_reply_recovers_nothing():
    """An earlier round's tool-calling reply is history, not this run's reply."""
    executor = make_executor(make_context(None, {"messages": []}))
    earlier_round = AIMessage(content="", tool_calls=[{"name": "write_file", "args": {}, "id": "call_1"}])
    assert executor._latest_reply is None

    with patch(TRACKER_PATH, return_value=MagicMock(last_finish_reason="length")):
        assert await executor._handle_length_truncation([HumanMessage(content="hi"), earlier_round]) is False
    assert await executor._handle_empty_response([HumanMessage(content="hi"), earlier_round]) is False
    assert executor._compactor.events == []
