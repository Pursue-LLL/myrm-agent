"""Tests for the execution trace record types."""

from myrm_agent_harness.agent.event_log.trace_types import ExecutionTrace, LLMCallRecord, ToolCallRecord


def test_llm_call_record_cache_read_tokens() -> None:
    """LLMCallRecord retains cache_read_tokens and exports it through ExecutionTrace.to_dict."""
    record = LLMCallRecord(
        sequence=1,
        start_time=100.0,
        end_time=102.5,
        model_name="deepseek-chat",
        duration_ms=2500.0,
        ttft_ms=650.0,
        prompt_tokens=1500,
        completion_tokens=300,
        total_tokens=1800,
        cache_read_tokens=1200,
    )
    assert record.cache_read_tokens == 1200

    trace = ExecutionTrace(
        session_id="test-session-123",
        llm_calls=[record],
        tool_calls=[
            ToolCallRecord(
                sequence=2,
                tool_name="web_search",
                start_time=103.0,
                end_time=105.0,
                duration_ms=2000.0,
                success=True,
            )
        ],
    )

    data = trace.to_dict()
    assert len(data["llm_calls"]) == 1
    assert data["llm_calls"][0]["cache_read_tokens"] == 1200
    assert data["llm_calls"][0]["model_name"] == "deepseek-chat"
