"""A tool call withheld as unsafe must end in a retry or a report, never in silence.

Argument text that is cut off or unparseable is never executed: the adapter records it
in ``additional_kwargs["tool_call_recovery"]`` and emits no ``tool_calls``. LangGraph
ends a turn whose last AI message has no tool calls, so these tests drive the real
``create_agent`` loop through ``StreamExecutor.execute()`` to prove recovery sees that
message, retries once with a larger output budget, and stays bounded. The same recovery
on a turn resumed after an approval is covered in ``test_redrive_from_thread.py``.
"""

from unittest.mock import MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage

from myrm_agent_harness.agent.streaming.event_handlers import process_updates_chunk
from myrm_agent_harness.agent.streaming.stream_executor import StreamExecutor
from myrm_agent_harness.agent.types import AgentRunStatistics
from myrm_agent_harness.toolkits.llms.ephemeral_output_tokens import reset_ephemeral_max_output_tokens
from myrm_agent_harness.toolkits.llms.errors import MyrmLLMError

from .scripted_agent import (
    BASE_MAX_TOKENS,
    CUT_ARGUMENTS,
    FULL_REPORT,
    TRACKER_PATH,
    adapter_message,
    complete_write,
    final_answer,
    make_context,
    make_executor,
    raw_write,
    run_agent,
    withheld_message,
)


@pytest.fixture(autouse=True)
def _isolated_output_budget():
    reset_ephemeral_max_output_tokens()
    yield
    reset_ephemeral_max_output_tokens()


# ---------------------------------------------------------------------------
# Real agent loop
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_success_path_is_untouched():
    run, _ = await run_agent([complete_write(), final_answer()])

    assert run.error is None
    assert run.executed == [("report.md", FULL_REPORT)]
    assert run.truncation_steps == []
    assert [request.max_tokens for request in run.requests] == [BASE_MAX_TOKENS] * 2


@pytest.mark.asyncio
async def test_output_cut_inside_a_call_is_retried_once_with_a_larger_budget():
    cut = (withheld_message(), "length")

    run, _ = await run_agent([cut, complete_write(), final_answer()])

    assert run.error is None
    assert run.executed == [("report.md", FULL_REPORT)]  # the cut file body was never written
    assert [request.max_tokens for request in run.requests[:2]] == [BASE_MAX_TOKENS, 2 * BASE_MAX_TOKENS]
    assert run.truncation_steps == ["tool_call_retry"]
    retry_event = next(event for event in run.compactor.status_events if event["step_key"] == "tool_call_retry")
    assert retry_event["restart"] is True


@pytest.mark.asyncio
async def test_retry_request_only_appends_to_the_first_request():
    """Prompt-cache invariant: the retry re-sends the original prefix byte for byte and only appends.

    The thread keeps the withheld call, so the model sees it answered by an invalid-arguments result before the hint.
    """
    run, _ = await run_agent([(withheld_message(), "length"), complete_write(), final_answer()])

    first, retry = run.requests[0], run.requests[1]
    assert retry.messages[: len(first.messages)] == first.messages
    appended = retry.messages[len(first.messages) :]
    assert [role for role, _ in appended] == ["AIMessage", "ToolMessage", "HumanMessage"]
    assert "arguments were invalid" in appended[1][1]
    assert "not executed" in appended[2][1]
    assert "retry" in appended[2][1].lower()


@pytest.mark.asyncio
async def test_provider_reporting_a_normal_finish_is_still_recovered():
    """The cut is detected from the arguments themselves, not from the provider's finish_reason."""
    lying = (withheld_message(stream_complete=True), "tool_calls")

    run, _ = await run_agent([lying, complete_write(), final_answer()])

    assert run.error is None
    assert run.executed == [("report.md", FULL_REPORT)]
    assert run.truncation_steps == ["tool_call_retry"]


@pytest.mark.asyncio
async def test_unparseable_arguments_are_retried():
    garbage = (withheld_message("{{{ this is not json at all", stream_complete=None), "tool_calls")

    run, _ = await run_agent([garbage, complete_write(), final_answer()])

    assert run.error is None
    assert run.executed == [("report.md", FULL_REPORT)]
    assert run.truncation_steps == ["tool_call_retry"]


@pytest.mark.asyncio
async def test_hopeless_truncation_is_bounded_and_reported():
    cut = (withheld_message(), "length")

    run, model = await run_agent([cut, cut])

    assert run.error is None  # a third (unscripted) model call would have surfaced as an error
    assert len(model.requests) == 2
    assert run.executed == []
    assert run.truncation_steps == ["tool_call_retry", "tool_call_truncated"]


@pytest.mark.asyncio
async def test_complete_calls_next_to_a_withheld_one_still_run_and_the_model_is_told():
    two_calls = [
        raw_write("call_a", '{"path": "notes.md", "content": "short note"}'),
        raw_write("call_b", CUT_ARGUMENTS),
    ]
    mixed = (adapter_message(two_calls, stream_complete=False), "length")

    run, _ = await run_agent([mixed, final_answer()])

    assert run.error is None
    assert run.executed == [("notes.md", "short note")]
    assert run.truncation_steps == []  # the turn went on, so the model itself sees the failed call
    tool_reports = [content for role, content in run.requests[1].messages if role == "ToolMessage"]
    assert any("arguments were invalid" in report for report in tool_reports)


# ---------------------------------------------------------------------------
# Handlers in isolation
# ---------------------------------------------------------------------------


def _handler_executor(agent_input: object) -> StreamExecutor:
    return make_executor(make_context(None, agent_input))


@pytest.mark.asyncio
@pytest.mark.parametrize("finish_reason", ["length", "max_tokens", "tool_calls", "stop", None])
async def test_withheld_call_triggers_a_retry_whatever_the_provider_reports(finish_reason: str | None):
    executor = _handler_executor({"messages": []})

    with patch(TRACKER_PATH, return_value=MagicMock(last_finish_reason=finish_reason)):
        retried = await executor._handle_length_truncation([withheld_message()])

    assert retried is True
    assert executor._tool_truncation_retries == 1
    assert executor._compactor.steps == ["tool_call_retry"]


@pytest.mark.asyncio
async def test_repaired_call_without_a_length_cut_is_not_retried():
    repaired = AIMessage(
        content="",
        additional_kwargs={
            "tool_call_recovery": [{"tool_call_id": "call_1", "strategy": "truncated_completion", "safe": True}]
        },
    )
    executor = _handler_executor({"messages": []})

    with patch(TRACKER_PATH, return_value=MagicMock(last_finish_reason="stop")):
        retried = await executor._handle_length_truncation([repaired])

    assert retried is False
    assert executor._compactor.events == []


@pytest.mark.asyncio
async def test_exhausted_retry_reports_instead_of_looping():
    executor = _handler_executor({"messages": []})
    executor._tool_truncation_retries = executor._MAX_TOOL_TRUNCATION_RETRIES

    with patch(TRACKER_PATH, return_value=MagicMock(last_finish_reason="stop")):
        retried = await executor._handle_length_truncation([withheld_message()])

    assert retried is False
    assert executor._compactor.steps == ["tool_call_truncated"]


@pytest.mark.asyncio
async def test_withheld_call_is_not_mistaken_for_an_empty_response():
    """Otherwise empty-response recovery would stack on top and finally raise ``MyrmLLMError``."""
    executor = _handler_executor({"messages": []})

    assert await executor._handle_empty_response([withheld_message()], retries=5) is False
    with pytest.raises(MyrmLLMError):
        await executor._handle_empty_response([AIMessage(content="")], retries=5)


async def _collect_from_updates(messages: list[BaseMessage]) -> list[BaseMessage]:
    collected: list[BaseMessage] = []
    updates: dict[str, dict[str, object]] = {"model": {"messages": messages}}
    async for _ in process_updates_chunk(updates, AgentRunStatistics(), "msg", collected_messages=collected):
        pass
    return collected


@pytest.mark.asyncio
async def test_update_stream_keeps_a_message_that_only_records_a_withheld_call():
    withheld = withheld_message()

    assert await _collect_from_updates([withheld]) == [withheld]


@pytest.mark.asyncio
async def test_update_stream_still_drops_a_truly_empty_ai_message():
    assert await _collect_from_updates([AIMessage(content="")]) == []


@pytest.mark.asyncio
async def test_update_stream_keeps_tool_results_in_order():
    result = ToolMessage(content="wrote report.md", tool_call_id="call_ok", name="write_file")
    answer = AIMessage(content="Done")

    assert await _collect_from_updates([result, answer]) == [result, answer]
