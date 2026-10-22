"""StreamTrace folds an agent event stream into the eval AgentResponse."""

from __future__ import annotations

from myrm_agent_harness.agent.errors import ToolErrorCategory

from app.core.eval.stream_trace import StreamTrace


def test_message_chunks_join_into_answer() -> None:
    trace = StreamTrace()
    trace.consume({"type": "message", "data": "Hello "})
    trace.consume({"type": "message", "data": "world"})
    trace.consume({"type": "message", "data": {"not": "text"}})

    assert trace.to_response(elapsed_ms=1.5).answer == "Hello world"


def test_tool_step_records_name_detail_and_error() -> None:
    trace = StreamTrace()
    trace.consume({"type": "tasks_steps", "tool_name": "web_search", "step_key": "s1", "data": [{"q": "x"}]})
    trace.consume({"type": "tasks_steps", "step_key": "s2", "status": "error", "error": "e" * 400})

    response = trace.to_response(elapsed_ms=0.0)

    assert response.tools_called == ["web_search", "s2"]
    assert response.tool_call_details[0] == {"tool_name": "web_search", "step_key": "s1", "detail": [{"q": "x"}]}
    assert response.tool_call_details[1]["error"] == "e" * 300
    assert response.blocked_count == 0


def test_benchmark_blocked_step_counts_toward_blocked_count() -> None:
    trace = StreamTrace()
    blocked = {"type": "tasks_steps", "tool_name": "web_fetch", "error_category": ToolErrorCategory.BENCHMARK_BLOCKED.value}
    trace.consume(blocked)
    trace.consume(blocked)

    response = trace.to_response(elapsed_ms=0.0)

    assert response.blocked_count == 2
    assert response.tool_call_details[0]["error_category"] == ToolErrorCategory.BENCHMARK_BLOCKED.value


def test_limit_markers_cover_engine_and_iteration_caps() -> None:
    engine = StreamTrace()
    engine.consume({"type": "engine_limit_reached", "data": {"limit_type": "max_tool_calls"}})
    iteration = StreamTrace()
    iteration.consume({"type": "iteration_limit_reached"})
    empty = StreamTrace()
    empty.consume({"type": "engine_limit_reached", "data": {"limit_type": ""}})

    assert engine.to_response(elapsed_ms=0.0).limit_reached == "max_tool_calls"
    assert iteration.to_response(elapsed_ms=0.0).limit_reached == "max_iterations"
    assert empty.to_response(elapsed_ms=0.0).limit_reached is None


def test_token_usage_accumulates_canonical_keys() -> None:
    trace = StreamTrace()
    trace.consume({"type": "token_usage", "data": {"usage": {"prompt_tokens": 10, "completion_tokens": 4}}})
    trace.consume({"type": "token_usage", "data": {"usage": {"prompt_tokens": 5, "completion_tokens": None}}})
    trace.consume({"type": "token_usage", "data": {"usage": "malformed"}})

    response = trace.to_response(elapsed_ms=12.0)

    assert response.token_usage == {"input_tokens": 15, "output_tokens": 4, "total_tokens": 19}
    assert response.extra_timings == {"execution_ms": 12.0}


def test_unknown_event_types_are_ignored() -> None:
    trace = StreamTrace()
    trace.consume({"type": "heartbeat", "data": "x"})

    response = trace.to_response(elapsed_ms=0.0)

    assert response.answer == ""
    assert response.tools_called == []
    assert response.token_usage["total_tokens"] == 0


def test_restart_drops_only_the_in_flight_segment() -> None:
    trace = StreamTrace()
    trace.consume({"type": "message", "data": "Let me check. "})
    trace.consume({"type": "tool_start"})
    trace.consume({"type": "message", "data": "The capital of France is Pa"})
    trace.consume({"type": "status", "step_key": "model_failover", "restart": True})
    trace.consume({"type": "message", "data": "Paris."})

    assert trace.to_response(elapsed_ms=0.0).answer == "Let me check. Paris."
