import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from myrm_agent_harness.utils.runtime.cancellation import CancellationToken, CancelReason

from app.core.utils.chat_utils import convert_chat_history
from app.services.agent.stream_session.stream_finalize import (
    finalize_agent_stream_session,
    yield_stream_exception_chunks,
)
from app.services.agent.stream_session.stream_loop import ApprovalTimeoutHolder, ClarificationTimeoutHolder
from app.services.agent.stream_session.stream_session_types import AgentStreamSession
from app.services.agent.streaming_support.stream_collector import StreamContentCollector


@pytest.mark.asyncio
async def test_stream_collector_agent_cancelled_event():
    collector = StreamContentCollector(chat_id="test_chat_1")
    collector.feed_event(
        {
            "type": "message",
            "data": "Hello world, I am generating something...",
            "messageId": "msg_123",
        }
    )
    collector.feed_event(
        {
            "type": "agent_cancelled",
            "data": {"reason": "user_cancelled"},
        }
    )

    extra_data = collector.extra_data
    assert extra_data is not None
    assert extra_data.get("completionStatus") == "cancelled"
    assert extra_data.get("stopReason") == {
        "code": "agent_cancelled",
        "category": "cancelled",
        "message": "Cancelled by user",
        "detail": {"reason": "user_cancelled"},
    }
    assert collector.content == "Hello world, I am generating something..."
    assert collector.has_persistable_turn is True


@pytest.mark.asyncio
async def test_stream_collector_cancelled_during_reasoning():
    collector = StreamContentCollector(chat_id="test_chat_reasoning")
    collector.feed_event(
        {
            "type": "reasoning",
            "data": "Thinking about how to solve this step by step...",
            "messageId": "msg_reasoning_1",
        }
    )
    collector.feed_event(
        {
            "type": "agent_cancelled",
            "data": {"reason": "user_cancelled"},
        }
    )

    assert collector.content == ""
    assert collector.reasoning == "Thinking about how to solve this step by step..."
    assert collector.has_persistable_turn is True
    extra_data = collector.extra_data
    assert extra_data is not None
    assert extra_data.get("completionStatus") == "cancelled"
    assert extra_data.get("reasoning") == "Thinking about how to solve this step by step..."


@pytest.mark.asyncio
async def test_stream_collector_cancelled_with_tool_steps():
    collector = StreamContentCollector(chat_id="test_chat_tools")
    collector.feed_event(
        {
            "type": "tasks_steps",
            "step_key": "bash_code_execute_tool",
            "tool_name": "bash_code_execute_tool",
            "data": [{"text": "Running npm build..."}],
            "status": "running",
        }
    )
    collector.feed_event(
        {
            "type": "message",
            "data": "Building the project now...",
            "messageId": "msg_tool_1",
        }
    )
    collector.feed_event(
        {
            "type": "agent_cancelled",
            "data": {"reason": "user_cancelled"},
        }
    )

    extra_data = collector.extra_data
    assert extra_data is not None
    assert extra_data.get("completionStatus") == "cancelled"
    assert len(extra_data.get("progressSteps", [])) == 1
    assert extra_data["progressSteps"][0]["step_key"] == "bash_code_execute_tool"


@pytest.mark.asyncio
async def test_finalize_agent_stream_session_with_cancelled_turn():
    collector = StreamContentCollector(chat_id="test_chat_cancel")
    collector.feed_event(
        {
            "type": "message",
            "data": "Partial response before cancel",
            "messageId": "msg_cancel_1",
        }
    )
    collector.feed_event(
        {
            "type": "agent_cancelled",
            "data": {"reason": "user_cancelled"},
        }
    )

    cancel_token = CancellationToken()
    cancel_token.cancel(CancelReason.USER_CANCELLED)

    session = MagicMock(spec=AgentStreamSession)
    session.collector = collector
    session.request = MagicMock()
    session.request.chat_id = "test_chat_cancel"
    session.request.timezone = "UTC"
    session.request.message_id = "req_cancel_1"
    session.request.resume_value = None
    session.request.use_workflow = False
    session.stream_ttft_ms = 120
    session.extra_context = {}
    session.had_fatal_error = False
    session.migration_live_readiness_status = None
    session.params = MagicMock()
    session.params.message_id = "msg_cancel_1"
    session.params.enable_skill_manage = False
    session.cancel_token = cancel_token
    session.monitor = AsyncMock()
    session.turn_capability_terminal_recorded = True

    approval = ApprovalTimeoutHolder()
    clarification = ClarificationTimeoutHolder()
    from myrm_agent_harness.agent.security import user_credentials_ctx

    token_ctx = user_credentials_ctx.set(None)

    with (
        patch(
            "app.services.chat.chat_service.ChatService.persist_assistant_message_safe", new_callable=AsyncMock
        ) as mock_persist,
        patch(
            "app.services.agent.stream_session.migration_readiness_anchor.record_migration_first_turn_outcome",
            new_callable=AsyncMock,
        ),
        patch("app.services.copilot.run_digest_store.RunDigestStore.end_run"),
    ):
        await finalize_agent_stream_session(
            session=session,
            token_ctx=token_ctx,
            approval=approval,
            clarification=clarification,
        )

        assert mock_persist.called
        call_args = mock_persist.call_args
        assert call_args[0][0] == "test_chat_cancel"
        assert call_args[0][1] == "Partial response before cancel"
        persisted_extra = call_args[1]["extra_data"]
        assert persisted_extra["completionStatus"] == "cancelled"
        assert persisted_extra["stopReason"]["code"] == "agent_cancelled"


@pytest.mark.asyncio
async def test_yield_stream_exception_chunks_cancelled_error():
    collector = StreamContentCollector(chat_id="test_chat_exc")
    collector.feed_event(
        {
            "type": "message",
            "data": "Streaming chunk before disconnect",
            "messageId": "msg_exc_1",
        }
    )

    cancel_token = CancellationToken()
    session = MagicMock(spec=AgentStreamSession)
    session.collector = collector
    session.params = MagicMock()
    session.params.message_id = "msg_exc_1"
    session.request = MagicMock()
    session.request.chat_id = "test_chat_exc"
    session.cancel_token = cancel_token
    session.turn_capability_terminal_recorded = False

    with patch("app.services.agent.stream_session.stream_finalize._record_turn_capability_failed_once", new_callable=AsyncMock):
        chunks = []
        async for chunk in yield_stream_exception_chunks(session, asyncio.CancelledError()):
            chunks.append(chunk)

        assert cancel_token.is_cancelled
        assert session.collector._completion_status == "cancelled"


@pytest.mark.asyncio
async def test_chat_utils_history_conversion_with_cancelled_turn():
    history = [
        ["human", "What is Python?", {}],
        [
            "assistant",
            "Python is an interpreted...",
            {
                "completionStatus": "cancelled",
                "reasoning_content": "User wants a quick overview of Python...",
            },
        ],
    ]

    converted = await convert_chat_history(history)
    assert len(converted) == 2
    assert isinstance(converted[0], HumanMessage)
    assert converted[0].content == "What is Python?"
    assert isinstance(converted[1], AIMessage)
    assert converted[1].content == "Python is an interpreted..."
    assert converted[1].additional_kwargs.get("reasoning_content") == "User wants a quick overview of Python..."
