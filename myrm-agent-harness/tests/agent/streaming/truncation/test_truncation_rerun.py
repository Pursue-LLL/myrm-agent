"""The turn a truncation recovery re-runs: the messages it carries, its events, and its retry bounds."""

from unittest.mock import MagicMock, patch

import pytest
from langchain_core.messages import AIMessage

from ..scripted_agent import recover_length_cut
from .support import llm_with_max_tokens, make_executor


@pytest.mark.asyncio
async def test_tool_call_truncated_triggers_retry(mock_context):
    """When finish_reason=length + has tool_calls → auto-retry (first time)."""
    mock_context.agent_input = {"messages": []}
    executor = make_executor(mock_context)

    ai_msg = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "write_file",
                "args": {"path": "test.py", "content": "truncat"},
                "id": "call_1",
            }
        ],
    )
    collected_messages = [ai_msg]

    tracker_mock = MagicMock()
    tracker_mock.last_finish_reason = "length"

    with patch(
        "myrm_agent_harness.utils.token_economics.tracker.get_token_tracker",
        return_value=tracker_mock,
    ):
        result = await recover_length_cut(executor, collected_messages)

    assert result is True
    events = executor._compactor.events
    assert len(events) == 1
    assert events[0]["step_key"] == "tool_call_retry"
    assert events[0].get("restart") is True


@pytest.mark.asyncio
async def test_tool_call_truncated_exhausted_after_retry(mock_context):
    """After 1 retry, tool_call_truncated warning is emitted."""
    mock_context.agent_input = {"messages": []}
    executor = make_executor(mock_context)
    executor._tool_truncation_retries = 1

    ai_msg = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "write_file",
                "args": {"path": "test.py", "content": "truncat"},
                "id": "call_1",
            }
        ],
    )
    collected_messages = [ai_msg]

    tracker_mock = MagicMock()
    tracker_mock.last_finish_reason = "length"

    with patch(
        "myrm_agent_harness.utils.token_economics.tracker.get_token_tracker",
        return_value=tracker_mock,
    ):
        result = await recover_length_cut(executor, collected_messages)

    assert result is False
    events = executor._compactor.events
    assert len(events) == 1
    assert events[0]["step_key"] == "tool_call_truncated"


@pytest.mark.asyncio
async def test_text_continuation_for_normal_text_truncation(mock_context):
    """When finish_reason=length + normal text content + no tool_calls → auto-continue with text_continuation event."""
    mock_context.agent_input = {"messages": []}
    executor = make_executor(mock_context)

    ai_msg = AIMessage(content="Some normal text that got truncated...")
    collected_messages = [ai_msg]

    tracker_mock = MagicMock()
    tracker_mock.last_finish_reason = "length"

    with patch(
        "myrm_agent_harness.utils.token_economics.tracker.get_token_tracker",
        return_value=tracker_mock,
    ):
        result = await recover_length_cut(executor, collected_messages)

    assert result is True
    assert len(executor._compactor.events) == 1
    assert executor._compactor.events[0]["step_key"] == "text_continuation"


@pytest.mark.asyncio
async def test_locale_propagation(mock_context):
    """Diagnostic should use locale from merged_context."""
    mock_context.merged_context = {"locale": "zh-CN"}
    mock_context.agent_input = {"messages": []}
    executor = make_executor(mock_context)

    ai_msg = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "write_file",
                "args": {"path": "f.py", "content": "c"},
                "id": "call_1",
            }
        ],
    )
    collected_messages = [ai_msg]

    tracker_mock = MagicMock()
    tracker_mock.last_finish_reason = "length"

    with patch(
        "myrm_agent_harness.utils.token_economics.tracker.get_token_tracker",
        return_value=tracker_mock,
    ):
        result = await recover_length_cut(executor, collected_messages)

    assert result is True
    events = executor._compactor.events
    assert len(events) == 1
    assert events[0]["diagnostic_result"]["locale"] == "zh-CN"


@pytest.mark.asyncio
async def test_merged_context_none(mock_context):
    """merged_context=None → defaults to locale 'en'."""
    mock_context.merged_context = None
    mock_context.agent_input = {"messages": []}
    executor = make_executor(mock_context)

    ai_msg = AIMessage(
        content="",
        tool_calls=[{"name": "bash", "args": {"command": "ls"}, "id": "call_1"}],
    )
    collected_messages = [ai_msg]

    tracker_mock = MagicMock()
    tracker_mock.last_finish_reason = "length"

    with patch(
        "myrm_agent_harness.utils.token_economics.tracker.get_token_tracker",
        return_value=tracker_mock,
    ):
        result = await recover_length_cut(executor, collected_messages)

    assert result is True
    events = executor._compactor.events
    assert len(events) == 1
    assert events[0]["diagnostic_result"]["locale"] == "en"


@pytest.mark.asyncio
async def test_diagnostic_failure_still_emits_event(mock_context):
    """If diagnostic generation fails, event is still emitted without diagnostic_result."""
    mock_context.agent_input = {"messages": []}
    executor = make_executor(mock_context)
    executor._tool_truncation_retries = 1

    ai_msg = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "write_file",
                "args": {"path": "f.py", "content": "..."},
                "id": "call_1",
            }
        ],
    )
    collected_messages = [ai_msg]

    tracker_mock = MagicMock()
    tracker_mock.last_finish_reason = "length"

    with (
        patch(
            "myrm_agent_harness.utils.token_economics.tracker.get_token_tracker",
            return_value=tracker_mock,
        ),
        patch(
            "myrm_agent_harness.agent.errors.diagnostics.LLMErrorDiagnostic.diagnose_truncation",
            side_effect=Exception("i18n module broken"),
        ),
    ):
        result = await recover_length_cut(executor, collected_messages)

    assert result is False
    events = executor._compactor.events
    assert len(events) == 1
    assert events[0]["step_key"] == "tool_call_truncated"
    assert "diagnostic_result" not in events[0]


# ---------------------------------------------------------------------------
# Text continuation exhausted
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_text_continuation_exhausted(mock_context):
    """When retries >= _MAX_LENGTH_CONTINUE_RETRIES → text_continuation_exhausted."""
    mock_context.agent_input = {"messages": []}
    executor = make_executor(mock_context)

    ai_msg = AIMessage(content="Some text that keeps getting truncated...")
    collected_messages = [ai_msg]

    tracker_mock = MagicMock()
    tracker_mock.last_finish_reason = "length"

    with patch(
        "myrm_agent_harness.utils.token_economics.tracker.get_token_tracker",
        return_value=tracker_mock,
    ):
        result = await recover_length_cut(executor, collected_messages, retries=3)

    assert result is False
    events = executor._compactor.events
    assert len(events) == 1
    assert events[0]["step_key"] == "text_continuation_exhausted"


# ---------------------------------------------------------------------------
# Text continuation: message list correctness + streaming_final_answer reset
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_text_continuation_injects_prompt_and_resets_flag(mock_context):
    """Text continuation appends continuation prompt and resets streaming_final_answer."""
    from langchain_core.messages import HumanMessage

    mock_context.agent_input = {"messages": []}
    executor = make_executor(mock_context)
    executor.streaming_final_answer = True

    ai_msg = AIMessage(content="Truncated text content...")
    collected_messages = [ai_msg]

    tracker_mock = MagicMock()
    tracker_mock.last_finish_reason = "length"

    with patch(
        "myrm_agent_harness.utils.token_economics.tracker.get_token_tracker",
        return_value=tracker_mock,
    ):
        result = await recover_length_cut(executor, collected_messages)

    assert result is True
    assert executor.streaming_final_answer is False

    messages = mock_context.agent_input["messages"]
    assert len(messages) == 2
    assert messages[0] is ai_msg
    assert isinstance(messages[1], HumanMessage)
    assert "truncated" in messages[1].content.lower()


# ---------------------------------------------------------------------------
# Tool-call retry: message cleanup correctness
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tool_call_retry_drops_truncated_ai_message(mock_context):
    """Tool-call retry drops the truncated AI message and appends a retry hint."""
    from langchain_core.messages import HumanMessage

    mock_context.agent_input = {"messages": []}
    executor = make_executor(mock_context)
    executor.streaming_final_answer = True

    human_msg = HumanMessage(content="Write a file")
    ai_msg = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "write_file",
                "args": {"path": "f.py", "content": "..."},
                "id": "call_1",
            }
        ],
    )
    collected_messages = [human_msg, ai_msg]

    tracker_mock = MagicMock()
    tracker_mock.last_finish_reason = "length"

    with patch(
        "myrm_agent_harness.utils.token_economics.tracker.get_token_tracker",
        return_value=tracker_mock,
    ):
        result = await recover_length_cut(executor, collected_messages)

    assert result is True
    assert executor.streaming_final_answer is False

    messages = mock_context.agent_input["messages"]
    assert len(messages) == 2
    assert messages[0] is human_msg
    assert isinstance(messages[1], HumanMessage)
    hint = messages[1].content.lower()
    assert "not executed" in hint
    assert "retry" in hint
    assert executor._tool_truncation_retries == 1


@pytest.mark.asyncio
async def test_inline_reasoning_only_truncation_retries(mock_context):
    """A tag-only truncated reply must drive a retry, not stall as 'has content'."""
    mock_context.agent_input = {"messages": []}
    mock_context.llm = llm_with_max_tokens(8192)
    executor = make_executor(mock_context)

    ai_msg = AIMessage(content="<think>The user wants me to say DONE. This is a simple")
    collected_messages = [ai_msg]

    tracker_mock = MagicMock()
    tracker_mock.last_finish_reason = "length"

    with patch(
        "myrm_agent_harness.utils.token_economics.tracker.get_token_tracker",
        return_value=tracker_mock,
    ):
        result = await recover_length_cut(executor, collected_messages)

    assert result is True
    events = executor._compactor.events
    assert len(events) == 1
    assert events[0]["step_key"] == "thinking_budget_exhausted"
    # The reasoning-only draft is dropped and replaced by a direct-answer prompt.
    messages = mock_context.agent_input["messages"]
    assert ai_msg not in messages
    assert "minimal reasoning" in messages[-1].content
