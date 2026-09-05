"""Direct unit verification for session trace performance enrichment and Gantt waterfall."""

import sys
from pathlib import Path

# Add server and harness to path
server_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(server_root))
harness_src = server_root.parent.parent / "myrm-agent-harness" / "src"
sys.path.insert(0, str(harness_src))

from app.api.statistics.session_trace import _enrich_performance_and_gantt, _empty_trace_payload

def run_tests():
    print("[1/3] Testing empty trace payload default performance summary...")
    payload = _empty_trace_payload("test-sess-1", [])
    assert "performance_summary" in payload
    perf = payload["performance_summary"]
    assert perf["llm_duration_ms"] == 0.0
    assert perf["tool_duration_ms"] == 0.0
    assert perf["total_prompt_tokens"] == 0
    assert perf["total_cache_read_tokens"] == 0
    assert perf["prompt_cache_hit_ratio"] == 0.0
    assert perf["gantt_spans"] == []
    print("      PASS: empty payload defaults are intact.")

    print("[2/3] Testing happy path: timing, prompt cache hit ratio & sorted Gantt spans...")
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
    perf = trace_data["performance_summary"]
    assert perf["llm_duration_ms"] == 2500.0
    assert perf["tool_duration_ms"] == 2500.0
    assert perf["total_prompt_tokens"] == 2000
    assert perf["total_completion_tokens"] == 300
    assert perf["total_cache_read_tokens"] == 1800
    assert perf["prompt_cache_hit_ratio"] == 0.9

    spans = perf["gantt_spans"]
    assert len(spans) == 3
    assert spans[0]["type"] == "llm"
    assert spans[0]["start_time"] == 10.0
    assert spans[0]["cache_read_tokens"] == 800
    assert spans[1]["type"] == "tool"
    assert spans[1]["start_time"] == 11.5
    assert spans[2]["type"] == "llm"
    assert spans[2]["start_time"] == 14.0
    print("      PASS: durations (5000ms total), cache hit ratio (90%) and Gantt sorting verified.")

    print("[3/3] Testing zero tokens and error tool calls division safety...")
    trace_zero = {
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
    _enrich_performance_and_gantt(trace_zero)
    perf_zero = trace_zero["performance_summary"]
    assert perf_zero["prompt_cache_hit_ratio"] == 0.0
    assert perf_zero["llm_duration_ms"] == 0.0
    assert perf_zero["tool_duration_ms"] == 50.0
    assert len(perf_zero["gantt_spans"]) == 1
    assert perf_zero["gantt_spans"][0]["status"] == "error"
    print("      PASS: zero tokens safety guard and error status intact.")

    print("\nALL 3 TEST SUITES PASSED CLEANLY (0 ERROR, 0 WARNING).")

if __name__ == "__main__":
    run_tests()
