import pytest

from app.services.agent.streaming_support.stream_collector import (
    _MAX_REASONING_CHARS,
    ACTIVE_COLLECTORS,
    StreamContentCollector,
)


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
        {
            "type": "tasks_steps",
            "step_key": "step1",
            "tool_name": "tool1",
            "data": [{"item": "val"}],
            "count": 1,
        }
    )

    # 4. Test token_usage
    collector.feed_event(
        {"type": "token_usage", "data": {"usage": {"prompt_tokens": 10}}}
    )

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
            "stream_ttft_ms": 120,
            "model": "test_model",
            "usage_alert": {"alert": "high"},
        }
    )
    collector.feed_event(
        {"type": "error", "error": "temporary failure", "error_type": "runtime"}
    )
    collector.feed_event(
        {
            "type": "iteration_limit_reached",
            "data": {"limit": 50, "nodes_completed": 50},
        }
    )

    # 6. Test routing, privacy
    collector.feed_event({"type": "routing_decision", "data": {"tier": "reasoning"}})
    collector.feed_event(
        {"type": "privacy_level", "data": {"current_turn_level": "strict"}}
    )
    collector.feed_event({"type": "privacy_route", "data": {"route": "local"}})

    # 7. Test cache break
    collector.feed_event(
        {
            "type": "status",
            "step_key": "cache_break",
            "data": {"raw_reasons": ["ttl_expiry"]},
        }
    )

    # 7b. Test model failover STATUS + SSE notify persistence
    collector.feed_event(
        {
            "type": "status",
            "step_key": "model_failover",
            "error_kind": "auth",
            "fallback_model": "MiniMax-M3",
        }
    )
    collector.feed_event(
        {
            "type": "model_failover",
            "data": {
                "fromModel": "agnes",
                "toModel": "MiniMax-M3",
                "reason": "auth_permanent",
            },
        }
    )

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

    # Assert properties. The failover events (fed after "Hello "/"Thinking ")
    # discard the primary-model drafts — the fallback restarts the answer from
    # scratch, so only the post-failover "World" message is persisted.
    assert collector.content == "World"
    assert collector.reasoning is None
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
    assert extra["streamTtftMs"] == 120
    assert extra["modelName"] == "test_model"
    assert extra["usageAlert"]["alert"] == "high"
    assert extra["tokenEconomics"]["total_cache_savings_usd"] == 0.01
    assert extra["routingTier"] == "reasoning"
    assert extra["privacyLevel"] == "strict"
    assert extra["privacyRoute"] == "local"
    assert extra["cacheBreak"]["raw_reasons"] == ["ttl_expiry"]
    failover_steps = [
        step
        for step in extra["progressSteps"]
        if isinstance(step, dict)
        and str(step.get("step_key", "")).startswith("model_failover")
    ]
    assert len(failover_steps) == 1
    assert failover_steps[0]["step_key"] == "model_failover_auth"
    assert failover_steps[0]["items"][0]["text"] == "agnes → MiniMax-M3"
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
        "data": {
            "actionRequests": [
                {"action": "bash_code_execute_tool", "args": {"command": "echo hi"}}
            ]
        },
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
    collector.feed_event(
        {
            "type": "session_recording",
            "data": {
                "filename": "session-2025.webm",
                "preview_url": "/api/v1/files/vault/render?filepath=recordings/session-2025.webm&workspace=/tmp",
                "content_type": "video/webm",
            },
        }
    )

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
    collector.feed_event(
        {"type": "tool_approval_request", "data": {"actionRequests": []}}
    )
    assert collector.has_pending_hitl_replay() is True
    collector.cleanup()


def test_stream_collector_persists_clarification_required() -> None:
    ACTIVE_COLLECTORS.clear()
    collector = StreamContentCollector(chat_id="chat-clarify-persist")
    collector.feed_event(
        {
            "type": "clarification_required",
            "messageId": "msg-clarify-1",
            "data": {
                "type": "ask_question",
                "source": "deep_research",
                "title": "Framework choice",
                "form": {
                    "questions": [
                        {
                            "id": "framework",
                            "prompt": "Which framework?",
                            "options": [
                                {"id": "langchain", "label": "LangChain"},
                            ],
                        }
                    ]
                },
            },
        }
    )

    extra = collector.extra_data
    assert extra is not None
    clarification = extra.get("clarification")
    assert isinstance(clarification, dict)
    assert clarification.get("answered") is False
    assert clarification.get("isResumeMode") is False
    assert clarification.get("title") == "Framework choice"
    assert isinstance(clarification.get("form"), dict)

    collector.feed_event(
        {
            "type": "status",
            "messageId": "msg-clarify-1",
            "data": {"phase": "clarify", "status": "resolved"},
        }
    )
    extra_after = collector.extra_data
    assert extra_after is not None
    assert extra_after["clarification"]["answered"] is True
    collector.cleanup()


def test_stream_collector_persists_plan_confirmation_waiting() -> None:
    ACTIVE_COLLECTORS.clear()
    collector = StreamContentCollector(chat_id="chat-plan-persist")
    collector.feed_event(
        {
            "type": "status",
            "messageId": "msg-plan-1",
            "data": {
                "phase": "plan_confirm",
                "status": "waiting",
                "plan": "1. Research\n2. Write report",
            },
        }
    )

    extra = collector.extra_data
    assert extra is not None
    plan_confirmation = extra.get("planConfirmation")
    assert isinstance(plan_confirmation, dict)
    assert plan_confirmation.get("status") == "waiting"
    assert plan_confirmation.get("source") == "deep_research"
    assert "Research" in str(plan_confirmation.get("plan"))
    collector.cleanup()


def test_stream_collector_clamps_reasoning_and_marks_truncation() -> None:
    collector = StreamContentCollector()
    collector.feed_event(
        {"type": "reasoning", "data": "x" * (_MAX_REASONING_CHARS + 64)}
    )
    collector.feed_event({"type": "reasoning", "data": "y" * 128})

    extra = collector.extra_data
    assert extra is not None
    reasoning = extra.get("reasoning")
    assert isinstance(reasoning, str)
    assert len(reasoning) == _MAX_REASONING_CHARS
    assert extra["reasoningTruncated"] is True
    assert extra["reasoningCharLimit"] == _MAX_REASONING_CHARS


def test_stream_collector_reasoning_is_scrubbed_before_persist() -> None:
    collector = StreamContentCollector()
    collector.feed_event(
        {"type": "reasoning", "data": "api_key=sk-test-12345 /Users/alice/private"}
    )

    extra = collector.extra_data
    assert extra is not None
    reasoning = extra.get("reasoning")
    assert isinstance(reasoning, str)
    assert "sk-test-12345" not in reasoning
    assert "/Users/alice" not in reasoning


def test_model_failover_dedupes_when_reason_key_unmapped() -> None:
    """STATUS error_kind and an SSE reason without a direct key still collapse."""
    collector = StreamContentCollector(chat_id="chat-failover-unmapped")
    collector.feed_event(
        {
            "type": "status",
            "step_key": "model_failover",
            "error_kind": "model_not_found",
            "fallback_model": "MiniMax-M3",
        }
    )
    collector.feed_event(
        {
            "type": "model_failover",
            "data": {
                "fromModel": "agnes",
                "toModel": "MiniMax-M3",
                "reason": "provider_policy_blocked",
            },
        }
    )

    extra = collector.extra_data
    assert extra is not None
    failover_steps = [
        step
        for step in extra["progressSteps"]
        if isinstance(step, dict)
        and str(step.get("step_key", "")).startswith("model_failover")
    ]
    assert len(failover_steps) == 1
    assert failover_steps[0]["step_key"] == "model_failover_model_not_found"
    assert failover_steps[0]["items"][0]["text"] == "agnes → MiniMax-M3"
    collector.cleanup()


def test_safety_block_failover_persists_single_safety_step() -> None:
    """SAFETY_BLOCK SSE reason collapses with the STATUS safety_fallback_active step."""
    collector = StreamContentCollector(chat_id="chat-failover-safety")
    collector.feed_event(
        {
            "type": "status",
            "step_key": "safety_fallback_active",
            "error_kind": "safety_block",
            "fallback_model": "safety-mini",
        }
    )
    collector.feed_event(
        {
            "type": "model_failover",
            "data": {
                "fromModel": "agnes",
                "toModel": "safety-mini",
                "reason": "safety_block",
            },
        }
    )

    extra = collector.extra_data
    assert extra is not None
    failover_steps = [
        step
        for step in extra["progressSteps"]
        if isinstance(step, dict)
        and (
            str(step.get("step_key", "")).startswith("model_failover")
            or step.get("step_key") == "safety_fallback_active"
        )
    ]
    assert len(failover_steps) == 1
    assert failover_steps[0]["step_key"] == "safety_fallback_active"
    assert failover_steps[0]["items"][0]["text"] == "agnes → safety-mini"
    collector.cleanup()


def test_model_failover_keeps_full_label_when_status_arrives_last() -> None:
    """Real runtime order: SSE notify (fed synchronously) precedes the STATUS event.

    The STATUS event carries only the fallback model name; it must NOT overwrite
    the fuller ``from → to`` label persisted from the SSE channel.
    """
    collector = StreamContentCollector(chat_id="chat-failover-status-last")
    collector.feed_event(
        {
            "type": "model_failover",
            "data": {
                "fromModel": "openai/__e2e_nonexistent_model__",
                "toModel": "openai/deepseek-v4-flash",
                "reason": "auth_permanent",
            },
        }
    )
    collector.feed_event(
        {
            "type": "status",
            "step_key": "model_failover",
            "error_kind": "auth",
            "fallback_model": "deepseek-v4-flash",
        }
    )

    extra = collector.extra_data
    assert extra is not None
    failover_steps = [
        step
        for step in extra["progressSteps"]
        if isinstance(step, dict)
        and str(step.get("step_key", "")).startswith("model_failover")
    ]
    assert len(failover_steps) == 1
    assert failover_steps[0]["step_key"] == "model_failover_auth"
    assert (
        failover_steps[0]["items"][0]["text"]
        == "openai/__e2e_nonexistent_model__ → openai/deepseek-v4-flash"
    )
    collector.cleanup()


def test_model_failover_drops_partial_draft() -> None:
    """Real runtime order: primary streams partial text before failing.

    The failover event must discard the partial draft (content + reasoning) so
    the fallback's complete answer does not get spliced with the stale text in
    the persisted history.
    """
    collector = StreamContentCollector(chat_id="chat-failover-draft-drop")
    collector.feed_event({"type": "message", "data": "Partial draft "})
    collector.feed_event({"type": "reasoning", "data": "Thinking "})

    collector.feed_event(
        {
            "type": "model_failover",
            "data": {
                "fromModel": "openai/primary",
                "toModel": "openai/fallback",
                "reason": "api_error",
            },
        }
    )

    assert collector.content == ""
    assert collector.reasoning is None
    assert not collector.has_content

    collector.feed_event({"type": "message", "data": "Complete fallback answer"})
    assert collector.content == "Complete fallback answer"

    extra = collector.extra_data
    assert extra is not None
    failover_steps = [
        step
        for step in extra["progressSteps"]
        if isinstance(step, dict)
        and str(step.get("step_key", "")).startswith("model_failover")
    ]
    assert len(failover_steps) == 1
    assert failover_steps[0]["items"][0]["text"] == "openai/primary → openai/fallback"
    collector.cleanup()


def test_status_restart_true_discards_draft() -> None:
    """A restart STATUS step (e.g. transient_retry) discards the streamed draft.

    The harness marks every recovery that re-runs the answer from scratch with
    ``restart: true``; the collector must drop partial content so the persisted
    history only contains the regenerated answer.
    """
    collector = StreamContentCollector(chat_id="chat-status-restart")
    collector.feed_event({"type": "message", "data": "Partial draft "})
    collector.feed_event({"type": "reasoning", "data": "Thinking "})

    collector.feed_event(
        {
            "type": "status",
            "step_key": "transient_retry",
            "error_kind": "overloaded",
            "attempt": 1,
            "restart": True,
        }
    )

    assert collector.content == ""
    assert collector.reasoning is None
    assert not collector.has_content

    collector.feed_event({"type": "message", "data": "Retried answer"})
    assert collector.content == "Retried answer"
    collector.cleanup()


def test_status_without_restart_keeps_draft() -> None:
    """STATUS steps that do not restart the turn keep the streamed content."""
    collector = StreamContentCollector(chat_id="chat-status-no-restart")
    collector.feed_event({"type": "message", "data": "Keep this "})

    collector.feed_event(
        {
            "type": "status",
            "step_key": "memory_archived",
            "tokens_saved": 123,
        }
    )

    assert collector.content == "Keep this "
    collector.cleanup()


def test_model_escalated_discards_draft() -> None:
    """Escalation re-plays the turn with a stronger model; drop the draft.

    The draft is discarded and the escalation transition is persisted as a
    progress step (mirroring model_failover), so history replay shows which
    model switch happened even though the final answer was regenerated.
    """
    collector = StreamContentCollector(chat_id="chat-escalated-draft")
    collector.feed_event({"type": "message", "data": "Partial escalated text "})
    collector.feed_event({"type": "reasoning", "data": "escalation reasoning "})

    collector.feed_event(
        {
            "type": "model_escalated",
            "data": {
                "from_model": "openai/fast",
                "to_model": "openai/strong",
                "reason": "escalation",
                "restart": True,
            },
        }
    )

    assert collector.content == ""
    assert collector.reasoning is None
    assert collector.extra_data is not None
    progress_steps = collector.extra_data.get("progressSteps")
    assert progress_steps == [
        {
            "step_key": "model_escalated",
            "items": [{"text": "openai/fast → openai/strong"}],
            "status": "success",
        }
    ]

    collector.feed_event({"type": "message", "data": "Replayed with stronger model"})
    assert collector.content == "Replayed with stronger model"
    collector.cleanup()
