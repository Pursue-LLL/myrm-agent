"""A recovery that appends a hint and runs the turn again behaves the same on a resumed turn as on a fresh one.

A turn resumed after an approval is driven by a ``Command`` that LangGraph has already consumed, so it cannot be
fed to the graph a second time. Its thread (checkpoint) already holds everything the turn produced, so the re-run
is a continue-mode input that carries only the hint. The first half drives the real ``create_agent`` loop through
approval pauses; the second half pins what each handler leaves as the next input.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langgraph.types import Command

from myrm_agent_harness.agent.streaming.stream_executor import StreamExecutor
from myrm_agent_harness.core.message_origin import is_user_authored_human_message
from myrm_agent_harness.toolkits.llms.ephemeral_output_tokens import reset_ephemeral_max_output_tokens

from ..scripted_agent import (
    BASE_MAX_TOKENS,
    FULL_REPORT,
    TRACKER_PATH,
    complete_write,
    final_answer,
    make_context,
    make_executor,
    recover_empty_reply,
    recover_length_cut,
    run_agent,
    withheld_message,
)


@pytest.fixture(autouse=True)
def _isolated_output_budget():
    reset_ephemeral_max_output_tokens()
    yield
    reset_ephemeral_max_output_tokens()


# ---------------------------------------------------------------------------
# Real agent loop: the withheld call comes back after an approval
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_withheld_call_after_an_approval_is_retried_and_the_run_finishes():
    cut = (withheld_message(), "length")

    run, model = await run_agent(
        [complete_write("call_1"), cut, complete_write("call_2"), final_answer()],
        gated=True,
    )

    assert run.error is None
    assert run.executed == [("report.md", FULL_REPORT)] * 2  # each write ran only after its own approval
    assert run.approvals == 2  # the retried call asked again, and that second pause was answered too
    assert run.truncation_steps == ["tool_call_retry"]
    assert len(model.requests) == 4


@pytest.mark.asyncio
async def test_retry_after_an_approval_runs_with_a_larger_output_budget():
    run, _ = await run_agent(
        [complete_write("call_1"), (withheld_message(), "length"), complete_write("call_2"), final_answer()],
        gated=True,
    )

    assert [request.max_tokens for request in run.requests[1:3]] == [BASE_MAX_TOKENS, 2 * BASE_MAX_TOKENS]


@pytest.mark.asyncio
async def test_retry_after_an_approval_tells_the_model_what_failed():
    run, _ = await run_agent(
        [complete_write("call_1"), (withheld_message(), "length"), complete_write("call_2"), final_answer()],
        gated=True,
    )

    cut_request, retry_request = run.requests[1], run.requests[2]
    assert retry_request.messages[: len(cut_request.messages)] == cut_request.messages
    appended = retry_request.messages[len(cut_request.messages) :]
    assert [role for role, _ in appended] == ["AIMessage", "ToolMessage", "HumanMessage"]
    assert "arguments were invalid" in appended[1][1]
    assert "not executed" in appended[2][1]


@pytest.mark.asyncio
async def test_hopeless_truncation_after_an_approval_is_bounded_and_reported():
    cut = (withheld_message(), "length")

    run, model = await run_agent([complete_write("call_1"), cut, cut], gated=True)

    assert run.error is None  # a further (unscripted) model call would have surfaced as an error
    assert len(model.requests) == 3
    assert run.truncation_steps == ["tool_call_retry", "tool_call_truncated"]
    assert run.approvals == 1


@pytest.mark.asyncio
async def test_fresh_and_resumed_turns_recover_with_the_same_steps():
    cut = (withheld_message(), "length")
    fresh, _ = await run_agent([cut, complete_write("call_1"), final_answer()])
    resumed, _ = await run_agent([complete_write("call_1"), cut, complete_write("call_2"), final_answer()], gated=True)

    assert fresh.truncation_steps == resumed.truncation_steps == ["tool_call_retry"]


# ---------------------------------------------------------------------------
# Handlers: what the next input is, per kind of turn
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Recovery:
    """One handler, the message it reacts to, and what it must leave behind."""

    name: str
    reply: AIMessage
    finish_reason: str
    call: Callable[[StreamExecutor, list[BaseMessage]], Awaitable[bool]]
    step: str
    hint: str
    draft_dropped: bool
    """Whether a fresh turn drops the failed reply from the re-run input (the thread keeps it either way)."""


async def _length_truncation(executor: StreamExecutor, collected: list[BaseMessage]) -> bool:
    return await recover_length_cut(executor, collected)


async def _empty_response(executor: StreamExecutor, collected: list[BaseMessage]) -> bool:
    return await recover_empty_reply(executor, collected, retries=0)


RECOVERIES = [
    Recovery(
        "withheld tool call",
        withheld_message(),
        "length",
        _length_truncation,
        "tool_call_retry",
        "was not executed",
        draft_dropped=True,
    ),
    Recovery(
        "text continuation",
        AIMessage(content="The report says revenue gre"),
        "length",
        _length_truncation,
        "text_continuation",
        "Continue exactly where you left off",
        draft_dropped=False,
    ),
    Recovery(
        "reasoning-only truncation",
        AIMessage(content="<think>The user wants a report. This is a simple"),
        "length",
        _length_truncation,
        "thinking_budget_exhausted",
        "minimal reasoning",
        draft_dropped=True,
    ),
    Recovery(
        "empty response",
        AIMessage(content="<think>nothing visible to say</think>"),
        "stop",
        _empty_response,
        "",
        "completely empty",
        draft_dropped=False,
    ),
]
QUESTION = HumanMessage(content="Write the Q3 report")


def _executor(agent_input: object) -> StreamExecutor:
    executor = make_executor(make_context(None, agent_input))
    executor._ctx.llm = MagicMock(max_tokens=BASE_MAX_TOKENS, model_kwargs={}, model_name="scripted-model")
    return executor


def _next_messages(executor: StreamExecutor) -> list[BaseMessage]:
    next_input = executor._ctx.agent_input
    assert isinstance(next_input, dict), "the re-run must be fed a plain input, never the consumed Command"
    return list(next_input["messages"])


@pytest.mark.asyncio
@pytest.mark.parametrize("recovery", RECOVERIES, ids=lambda recovery: recovery.name)
async def test_fresh_turn_reruns_with_its_messages_and_the_hint(recovery: Recovery):
    executor = _executor({"messages": [QUESTION]})

    with patch(TRACKER_PATH, return_value=MagicMock(last_finish_reason=recovery.finish_reason)):
        retried = await recovery.call(executor, [QUESTION, recovery.reply])

    assert retried is True
    messages = _next_messages(executor)
    kept = [QUESTION] if recovery.draft_dropped else [QUESTION, recovery.reply]
    assert messages[:-1] == kept
    assert recovery.hint in str(messages[-1].content)
    assert executor.streaming_final_answer is False


@pytest.mark.asyncio
@pytest.mark.parametrize("recovery", RECOVERIES, ids=lambda recovery: recovery.name)
async def test_resumed_turn_reruns_with_only_the_hint(recovery: Recovery):
    """The thread holds the resumed turn already, so the re-run carries just the hint."""
    executor = _executor(Command(resume="approved"))

    with patch(TRACKER_PATH, return_value=MagicMock(last_finish_reason=recovery.finish_reason)):
        retried = await recovery.call(executor, [recovery.reply])

    assert retried is True
    messages = _next_messages(executor)
    assert len(messages) == 1
    assert recovery.hint in str(messages[0].content)
    assert executor.streaming_final_answer is False
    if recovery.step:
        assert recovery.step in executor._compactor.steps


@pytest.mark.asyncio
@pytest.mark.parametrize("resumed", [False, True], ids=["fresh", "resumed"])
@pytest.mark.parametrize("recovery", RECOVERIES, ids=lambda recovery: recovery.name)
async def test_hint_is_runtime_authored_not_a_user_message(recovery: Recovery, resumed: bool):
    """The approval intent ledger and the input guard read user words; a recovery hint is not one."""
    executor = _executor(Command(resume="approved") if resumed else {"messages": [QUESTION]})
    collected = [recovery.reply] if resumed else [QUESTION, recovery.reply]

    with patch(TRACKER_PATH, return_value=MagicMock(last_finish_reason=recovery.finish_reason)):
        await recovery.call(executor, collected)

    hint = _next_messages(executor)[-1]
    assert isinstance(hint, HumanMessage)
    assert is_user_authored_human_message(hint) is False
    assert is_user_authored_human_message(QUESTION) is True


@pytest.mark.asyncio
async def test_resumed_turn_keeps_the_retry_bounded():
    executor = _executor(Command(resume="approved"))
    executor._tool_truncation_retries = executor._MAX_TOOL_TRUNCATION_RETRIES

    with patch(TRACKER_PATH, return_value=MagicMock(last_finish_reason="length")):
        retried = await recover_length_cut(executor, [withheld_message()])

    assert retried is False
    assert executor._compactor.steps == ["tool_call_truncated"]
    assert isinstance(executor._ctx.agent_input, Command)  # nothing was re-driven


@pytest.mark.asyncio
async def test_resumed_turn_with_nothing_to_recover_keeps_its_command():
    executor = _executor(Command(resume="approved"))

    with patch(TRACKER_PATH, return_value=MagicMock(last_finish_reason="stop")):
        retried = await recover_length_cut(executor, [AIMessage(content="A complete answer.")])

    assert retried is False
    assert isinstance(executor._ctx.agent_input, Command)


@pytest.mark.asyncio
async def test_a_withheld_call_leaves_its_arguments_in_the_log(caplog: pytest.LogCaptureFixture):
    """The raw arguments exist only in memory; the retry must log what was cut before it moves on."""
    executor = _executor({"messages": [QUESTION]})

    with caplog.at_level("WARNING"), patch(TRACKER_PATH, return_value=MagicMock(last_finish_reason="length")):
        await recover_length_cut(executor, [QUESTION, withheld_message()])

    logged = " ".join(record.getMessage() for record in caplog.records)
    assert "write_file" in logged
    assert "Revenue grew by 1" in logged
