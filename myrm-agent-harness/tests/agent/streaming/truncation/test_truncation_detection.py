"""What kind of truncation a finished turn is: reasoning only, text, or a tool call, and when it is not one."""

from unittest.mock import MagicMock, patch

import pytest
from langchain_core.messages import AIMessage

from ..scripted_agent import recover_length_cut
from .support import llm_with_max_tokens, make_executor


@pytest.mark.asyncio
async def test_thinking_budget_exhausted_detected(mock_context):
    """When finish_reason=length + reasoning only + no tool_calls → thinking_budget_exhausted."""
    executor = make_executor(mock_context)
    mock_context.llm = llm_with_max_tokens(8192)

    ai_msg = AIMessage(
        content="",
        additional_kwargs={"reasoning_content": "Long reasoning chain that consumed all tokens..."},
    )
    collected_messages = [ai_msg]

    tracker_mock = MagicMock()
    tracker_mock.last_finish_reason = "length"

    with patch(
        "myrm_agent_harness.utils.token_economics.tracker.get_token_tracker",
        return_value=tracker_mock,
    ):
        await recover_length_cut(executor, collected_messages)

    events = executor._compactor.events
    assert len(events) == 1
    assert events[0]["step_key"] == "thinking_budget_exhausted"
    assert events[0]["messageId"] == "test_msg_id"
    assert "diagnostic_result" in events[0]
    assert events[0]["diagnostic_result"]["error_type"] == "thinking_budget_exhausted"


@pytest.mark.asyncio
async def test_no_truncation_when_finish_reason_stop(mock_context):
    """When finish_reason=stop → no truncation event emitted."""
    executor = make_executor(mock_context)

    ai_msg = AIMessage(content="Normal response")
    collected_messages = [ai_msg]

    tracker_mock = MagicMock()
    tracker_mock.last_finish_reason = "stop"

    with patch(
        "myrm_agent_harness.utils.token_economics.tracker.get_token_tracker",
        return_value=tracker_mock,
    ):
        await recover_length_cut(executor, collected_messages)

    assert len(executor._compactor.events) == 0


@pytest.mark.asyncio
async def test_no_truncation_when_no_tracker(mock_context):
    """When no tracker available → no truncation event."""
    executor = make_executor(mock_context)

    with patch(
        "myrm_agent_harness.utils.token_economics.tracker.get_token_tracker",
        return_value=None,
    ):
        await recover_length_cut(executor, [])

    assert len(executor._compactor.events) == 0


@pytest.mark.asyncio
async def test_max_tokens_finish_reason(mock_context):
    """max_tokens finish reason should also trigger detection (Anthropic)."""
    executor = make_executor(mock_context)
    mock_context.llm = llm_with_max_tokens(8192)

    ai_msg = AIMessage(
        content="",
        additional_kwargs={"reasoning_content": "Anthropic thinking block..."},
    )
    collected_messages = [ai_msg]

    tracker_mock = MagicMock()
    tracker_mock.last_finish_reason = "max_tokens"

    with patch(
        "myrm_agent_harness.utils.token_economics.tracker.get_token_tracker",
        return_value=tracker_mock,
    ):
        await recover_length_cut(executor, collected_messages)

    events = executor._compactor.events
    assert len(events) == 1
    assert events[0]["step_key"] == "thinking_budget_exhausted"


@pytest.mark.asyncio
async def test_anthropic_thinking_block_detection(mock_context):
    """Anthropic-style thinking blocks (content list with type=thinking) should be detected."""
    executor = make_executor(mock_context)
    mock_context.llm = llm_with_max_tokens(8192)

    ai_msg = AIMessage(
        content=[{"type": "thinking", "thinking": "Deep reasoning..."}],
    )
    collected_messages = [ai_msg]

    tracker_mock = MagicMock()
    tracker_mock.last_finish_reason = "max_tokens"

    with patch(
        "myrm_agent_harness.utils.token_economics.tracker.get_token_tracker",
        return_value=tracker_mock,
    ):
        await recover_length_cut(executor, collected_messages)

    events = executor._compactor.events
    assert len(events) == 1
    assert events[0]["step_key"] == "thinking_budget_exhausted"


@pytest.mark.asyncio
async def test_empty_collected_messages(mock_context):
    """No AIMessage in collected_messages → no event."""
    executor = make_executor(mock_context)

    tracker_mock = MagicMock()
    tracker_mock.last_finish_reason = "length"

    with patch(
        "myrm_agent_harness.utils.token_economics.tracker.get_token_tracker",
        return_value=tracker_mock,
    ):
        await recover_length_cut(executor, [])

    assert len(executor._compactor.events) == 0


@pytest.mark.asyncio
async def test_only_human_messages(mock_context):
    """Only HumanMessage in collected_messages → no event."""
    from langchain_core.messages import HumanMessage

    executor = make_executor(mock_context)

    collected_messages = [HumanMessage(content="Hello")]

    tracker_mock = MagicMock()
    tracker_mock.last_finish_reason = "length"

    with patch(
        "myrm_agent_harness.utils.token_economics.tracker.get_token_tracker",
        return_value=tracker_mock,
    ):
        await recover_length_cut(executor, collected_messages)

    assert len(executor._compactor.events) == 0


@pytest.mark.asyncio
async def test_tool_calls_with_reasoning_prioritizes_tool_call(mock_context):
    """When both tool_calls and reasoning present, should trigger tool-call retry."""
    mock_context.agent_input = {"messages": []}
    executor = make_executor(mock_context)

    ai_msg = AIMessage(
        content="",
        additional_kwargs={"reasoning_content": "Some reasoning..."},
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
    assert events[0]["step_key"] == "tool_call_retry"
    assert events[0].get("restart") is True


@pytest.mark.asyncio
async def test_tool_calls_with_content(mock_context):
    """tool_calls + regular content + length → tool-call retry (tool_calls take priority)."""
    mock_context.agent_input = {"messages": []}
    executor = make_executor(mock_context)

    ai_msg = AIMessage(
        content="Let me write the file for you.",
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
async def test_picks_last_ai_message(mock_context):
    """Should use the LAST AIMessage, not the first."""
    from langchain_core.messages import HumanMessage

    mock_context.agent_input = {"messages": []}
    executor = make_executor(mock_context)

    first_ai = AIMessage(content="First response")
    human = HumanMessage(content="Continue")
    last_ai = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "write_file",
                "args": {"path": "f.py", "content": "..."},
                "id": "call_1",
            }
        ],
    )
    collected_messages = [first_ai, human, last_ai]

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


# ---------------------------------------------------------------------------
# Edge: no content, no reasoning, no tool_calls → early return False
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_content_no_reasoning_no_tool_calls(mock_context):
    """AIMessage with empty content and no tool_calls → returns False, no event."""
    executor = make_executor(mock_context)

    ai_msg = AIMessage(content="")
    collected_messages = [ai_msg]

    tracker_mock = MagicMock()
    tracker_mock.last_finish_reason = "length"

    with patch(
        "myrm_agent_harness.utils.token_economics.tracker.get_token_tracker",
        return_value=tracker_mock,
    ):
        result = await recover_length_cut(executor, collected_messages)

    assert result is False
    assert len(executor._compactor.events) == 0


# ---------------------------------------------------------------------------
# _has_non_reasoning_content: list content with string items
# ---------------------------------------------------------------------------


def test_has_non_reasoning_content_list_with_strings():
    """_has_non_reasoning_content returns True for list content with non-empty strings."""
    from myrm_agent_harness.agent.streaming.recovery.stream_recovery_truncation import (
        StreamTruncationRecoveryMixin,
    )

    msg = MagicMock()
    msg.content = ["hello", "world"]
    assert StreamTruncationRecoveryMixin._has_non_reasoning_content(msg) is True

    msg.content = ["", "  "]
    assert StreamTruncationRecoveryMixin._has_non_reasoning_content(msg) is False


def test_has_non_reasoning_content_list_with_non_thinking_dict():
    """_has_non_reasoning_content returns True for non-thinking dict blocks."""
    from myrm_agent_harness.agent.streaming.recovery.stream_recovery_truncation import (
        StreamTruncationRecoveryMixin,
    )

    msg = MagicMock()
    msg.content = [{"type": "text", "text": "visible"}]
    assert StreamTruncationRecoveryMixin._has_non_reasoning_content(msg) is True

    msg.content = [{"type": "thinking", "thinking": "internal"}]
    assert StreamTruncationRecoveryMixin._has_non_reasoning_content(msg) is False


# ---------------------------------------------------------------------------
# Inline tag-wrapped reasoning (MiniMax inlines <think> in `content`)
#
# Live MiniMax probe: with a small max_tokens the model returns
# finish_reason=length and content="<think>…" with NO reasoning_content field.
# Treating that as user-visible content is what stalled the resumed turn.
# ---------------------------------------------------------------------------


def test_inline_reasoning_truncated_think_only():
    """Unclosed <think> (truncated mid-reasoning) is reasoning, not content."""
    from myrm_agent_harness.agent.streaming.recovery.stream_recovery_truncation import (
        StreamTruncationRecoveryMixin,
    )

    msg = AIMessage(content='<think>The user wants me to say "DONE". This is a simple')
    assert StreamTruncationRecoveryMixin._has_inline_reasoning(msg) is True


def test_inline_reasoning_closed_think_only():
    """A closed <think> block with nothing after it is reasoning, not content."""
    from myrm_agent_harness.agent.streaming.recovery.stream_recovery_truncation import (
        StreamTruncationRecoveryMixin,
    )

    msg = AIMessage(content="<think>deliberating</think>\n\n")
    assert StreamTruncationRecoveryMixin._has_inline_reasoning(msg) is True


def test_inline_reasoning_with_real_answer_is_content():
    """<think> followed by an actual answer must stay on the content path."""
    from myrm_agent_harness.agent.streaming.recovery.stream_recovery_truncation import (
        StreamTruncationRecoveryMixin,
    )

    msg = AIMessage(content="<think>deliberating</think>\n\nDONE")
    assert StreamTruncationRecoveryMixin._has_inline_reasoning(msg) is False


def test_inline_reasoning_plain_text_is_not_reasoning():
    """Plain text without thinking tags is never classified as reasoning."""
    from myrm_agent_harness.agent.streaming.recovery.stream_recovery_truncation import (
        StreamTruncationRecoveryMixin,
    )

    assert StreamTruncationRecoveryMixin._has_inline_reasoning(AIMessage(content="DONE")) is False
