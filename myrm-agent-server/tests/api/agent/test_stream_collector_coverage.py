import pytest

from app.services.agent.streaming_support.stream_collector import ACTIVE_COLLECTORS, StreamContentCollector


@pytest.mark.asyncio
async def test_stream_collector_full_coverage():
    # Clean up state
    ACTIVE_COLLECTORS.clear()

    collector = StreamContentCollector(chat_id="test_chat_1", sibling_group_id="sib_1")
    assert "test_chat_1" in ACTIVE_COLLECTORS

    # Test subscribe/unsubscribe
    snapshot, q = collector.subscribe()
    assert collector.has_subscribers
    collector.unsubscribe(q)
    assert not collector.has_subscribers

    # Subscribe again to receive events
    _, q2 = collector.subscribe()

    # 1. Test message and reasoning
    collector.feed_event({"type": "message", "data": "Hello "})
    collector.feed_event({"type": "reasoning", "data": "Thinking "})

    # 2. Test sources
    collector.feed_event({"type": "sources", "data": [{"url": "http://a.com"}]})

    # 3. Test tasks_steps
    collector.feed_event(
        {"type": "tasks_steps", "step_key": "step1", "tool_name": "tool1", "data": [{"item": "val"}], "count": 1}
    )

    # 4. Test token_usage
    collector.feed_event({"type": "token_usage", "data": {"usage": {"prompt_tokens": 10}}})

    # 5. Test message_end
    collector.feed_event(
        {
            "type": "message_end",
            "usage": {"total_tokens": 20},
            "token_economics": {"total_cache_savings_usd": 0.01},
            "context_budget": {"used": 50},
            "cost_usd": 0.05,
            "cost_status": "calculated",
            "completion_status": "success",
            "model": "test_model",
            "usage_alert": {"alert": "high"},
        }
    )
    collector.feed_event({"type": "error", "error": "temporary failure", "error_type": "runtime"})
    collector.feed_event({"type": "iteration_limit_reached", "data": {"limit": 50, "nodes_completed": 50}})

    # 6. Test routing, privacy
    collector.feed_event({"type": "routing_decision", "data": {"tier": "reasoning"}})
    collector.feed_event({"type": "privacy_level", "data": {"current_turn_level": "strict"}})
    collector.feed_event({"type": "privacy_route", "data": {"route": "local"}})

    # 7. Test cache break
    collector.feed_event({"type": "status", "step_key": "cache_break", "data": {"raw_reasons": ["ttl_expiry"]}})

    # 8. Test memory recall tool end
    collector.feed_event(
        {
            "type": "tool_end",
            "tool_name": "memory_search_tool",
            "cited_memory_ids": ["m1", "m2"],
            "cited_memory_refs": [{"id": "m1", "text": "ref1"}],
            "memory_retrieval_trace": {"id": "t1", "details": "trace1"},
        }
    )

    # 9. Test feed_sse wrapper
    collector.feed_sse('data: {"type": "message", "data": "World"}\n\n')
    # Invalid SSE
    collector.feed_sse("invalid")
    collector.feed_sse("data: invalid_json\n\n")

    # Assert properties
    assert collector.content == "Hello World"
    assert collector.reasoning == "Thinking "
    assert collector.has_content is True
    assert collector.sibling_group_id == "sib_1"

    extra = collector.extra_data
    assert extra is not None
    assert extra["sources"][0]["url"] == "http://a.com"
    assert extra["progressSteps"][0]["step_key"] == "step1"
    assert extra["usage"]["total_tokens"] == 20
    assert extra["contextBudget"]["used"] == 50
    assert extra["costUsd"] == 0.05
    assert extra["costStatus"] == "calculated"
    assert extra["completionStatus"] == "success"
    assert extra["modelName"] == "test_model"
    assert extra["usageAlert"]["alert"] == "high"
    assert extra["tokenEconomics"]["total_cache_savings_usd"] == 0.01
    assert extra["routingTier"] == "reasoning"
    assert extra["privacyLevel"] == "strict"
    assert extra["privacyRoute"] == "local"
    assert extra["cacheBreak"]["raw_reasons"] == ["ttl_expiry"]
    assert extra["citedMemoryIds"] == ["m1", "m2"]
    assert extra["citedMemoryRefs"][0]["id"] == "m1"
    assert extra["memoryRetrievalTraces"][0]["id"] == "t1"
    assert extra["stopReason"]["code"] == "iteration_limit_reached"
    assert extra["stopReason"]["category"] == "limit"

    # Cleanup
    collector.cleanup()
    assert "test_chat_1" not in ACTIVE_COLLECTORS


def test_stream_collector_replays_pending_interrupts_to_late_subscriber() -> None:
    ACTIVE_COLLECTORS.clear()
    collector = StreamContentCollector(chat_id="chat-interrupt-replay")
    approval = {
        "type": "tool_approval_request",
        "messageId": "msg-1",
        "data": {"actionRequests": [{"action": "bash_code_execute_tool", "args": {"command": "echo hi"}}]},
    }
    collector.feed_event(approval)
    _snapshot, queue = collector.subscribe()
    assert queue.get_nowait() == approval
    collector.cleanup()


@pytest.mark.asyncio
async def test_stream_collector_session_recording():
    """session_recording event is collected and included in extra_data."""
    ACTIVE_COLLECTORS.clear()
    collector = StreamContentCollector(chat_id="test_recording")

    collector.feed_event({"type": "message", "data": "test content"})
    collector.feed_event({
        "type": "session_recording",
        "data": {
            "filename": "session-2025.webm",
            "preview_url": "/api/v1/files/vault/render?filepath=recordings/session-2025.webm&workspace=/tmp",
            "content_type": "video/webm",
        },
    })

    assert collector.has_content
    extra = collector.extra_data
    assert extra is not None
    assert "sessionRecording" in extra
    assert extra["sessionRecording"]["filename"] == "session-2025.webm"
    assert "preview_url" in extra["sessionRecording"]
    assert extra["sessionRecording"]["content_type"] == "video/webm"

    collector.cleanup()


@pytest.mark.asyncio
async def test_stream_collector_session_recording_via_sse():
    """session_recording event via feed_sse is correctly parsed and persisted."""
    ACTIVE_COLLECTORS.clear()
    collector = StreamContentCollector(chat_id="test_rec_sse")

    sse_chunk = 'data: {"type": "session_recording", "data": {"filename": "rec.webm", "preview_url": "/vault/render?f=rec.webm", "content_type": "video/webm"}}\n\n'
    collector.feed_sse(sse_chunk)

    extra = collector.extra_data
    assert extra is not None
    assert extra["sessionRecording"]["filename"] == "rec.webm"

    collector.cleanup()


@pytest.mark.asyncio
async def test_stream_collector_session_recording_absent():
    """When no session_recording event is fed, extra_data does not contain sessionRecording."""
    ACTIVE_COLLECTORS.clear()
    collector = StreamContentCollector(chat_id="test_no_rec")

    collector.feed_event({"type": "message", "data": "hello"})
    collector.feed_event({"type": "routing_decision", "data": {"tier": "fast"}})

    extra = collector.extra_data
    assert extra is not None
    assert "sessionRecording" not in extra
    assert extra["routingTier"] == "fast"

    collector.cleanup()


def test_stream_collector_cleanup_only_removes_self_from_registry() -> None:
    ACTIVE_COLLECTORS.clear()
    first = StreamContentCollector(chat_id="chat-cleanup-race")
    second = StreamContentCollector(chat_id="chat-cleanup-race")
    assert ACTIVE_COLLECTORS["chat-cleanup-race"] is second
    first.cleanup()
    assert ACTIVE_COLLECTORS["chat-cleanup-race"] is second
    second.cleanup()
    assert "chat-cleanup-race" not in ACTIVE_COLLECTORS


def test_stream_collector_has_pending_hitl_replay() -> None:
    ACTIVE_COLLECTORS.clear()
    collector = StreamContentCollector(chat_id="chat-hitl-pending")
    assert collector.has_pending_hitl_replay() is False
    collector.feed_event({"type": "tool_approval_request", "data": {"actionRequests": []}})
    assert collector.has_pending_hitl_replay() is True
    collector.cleanup()
