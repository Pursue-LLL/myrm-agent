"""Unit tests for session trace performance enrichment and Gantt waterfall generation."""

import pytest
from app.api.statistics.session_trace import _enrich_performance_and_gantt, _empty_trace_payload


def test_empty_trace_payload_contains_performance_summary():
    """Verify empty trace payload contains default performance summary structure."""
    payload = _empty_trace_payload("test-sess-1", [])
    assert "performance_summary" in payload
    perf = payload["performance_summary"]
    assert perf["llm_duration_ms"] == 0.0
    assert perf["tool_duration_ms"] == 0.0
    assert perf["total_prompt_tokens"] == 0
    assert perf["total_cache_read_tokens"] == 0
    assert perf["prompt_cache_hit_ratio"] == 0.0
    assert perf["gantt_spans"] == []


def test_enrich_performance_and_gantt_happy_path():
    """Verify accurate aggregation of durations, cache hit ratio and sorted Gantt spans."""
    trace_data = {
        "llm_calls": [
            {
                "sequence": 1,
                "model_name": "deepseek-v3",
                "duration_ms": 1500.0,
                "start_time": 10.0,
                "end_time": 11.5,
                "ttft_ms": 450.0,
                "prompt_tokens": 1000,
                "completion_tokens": 200,
                "cache_read_tokens": 800,
            },
            {
                "sequence": 3,
                "model_name": "deepseek-v3",
                "duration_ms": 1000.0,
                "start_time": 14.0,
                "end_time": 15.0,
                "ttft_ms": 300.0,
                "prompt_tokens": 1000,
                "completion_tokens": 100,
                "cache_read_tokens": 1000,
            },
        ],
        "tool_calls": [
            {
                "sequence": 2,
                "tool_name": "web_search",
                "duration_ms": 2500.0,
                "start_time": 11.5,
                "end_time": 14.0,
                "success": True,
            }
        ],
    }

    _enrich_performance_and_gantt(trace_data)

    assert "performance_summary" in trace_data
    perf = trace_data["performance_summary"]
    assert perf["llm_duration_ms"] == 2500.0
    assert perf["tool_duration_ms"] == 2500.0
    assert perf["total_prompt_tokens"] == 2000
    assert perf["total_completion_tokens"] == 300
    assert perf["total_cache_read_tokens"] == 1800
    # 1800 / 2000 = 0.9 (90% cache hit ratio)
    assert perf["prompt_cache_hit_ratio"] == 0.9

    spans = perf["gantt_spans"]
    assert len(spans) == 3
    # Verify temporal sorting
    assert spans[0]["type"] == "llm"
    assert spans[0]["start_time"] == 10.0
    assert spans[0]["cache_read_tokens"] == 800

    assert spans[1]["type"] == "tool"
    assert spans[1]["start_time"] == 11.5
    assert spans[1]["label"] == "web_search"

    assert spans[2]["type"] == "llm"
    assert spans[2]["start_time"] == 14.0
    assert spans[2]["cache_read_tokens"] == 1000


def test_enrich_performance_zero_tokens_division_safety():
    """Verify division-by-zero protection when prompt tokens is zero."""
    trace_data = {
        "llm_calls": [],
        "tool_calls": [
            {
                "sequence": 1,
                "tool_name": "local_cmd",
                "duration_ms": 50.0,
                "start_time": 1.0,
                "end_time": 1.05,
                "success": False,
                "error": "Command failed",
            }
        ],
    }

    _enrich_performance_and_gantt(trace_data)
    perf = trace_data["performance_summary"]
    assert perf["prompt_cache_hit_ratio"] == 0.0
    assert perf["llm_duration_ms"] == 0.0
    assert perf["tool_duration_ms"] == 50.0
    assert len(perf["gantt_spans"]) == 1
    assert perf["gantt_spans"][0]["status"] == "error"
    assert perf["gantt_spans"][0]["error"] == "Command failed"
