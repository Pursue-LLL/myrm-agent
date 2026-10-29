"""The CLI summary prints the figures the session summary exports, read from the producers' own keys."""

from __future__ import annotations

import pytest

from myrm_agent_harness.agent.context_management.tracking.task_metrics_model import TaskMetrics
from myrm_agent_harness.agent.event_log.cli_summary import generate_cli_summary
from myrm_agent_harness.agent.event_log.types import SessionSummary
from myrm_agent_harness.utils.token_economics.tracker import TokenTracker


@pytest.fixture(scope="module")
def printed() -> str:
    tracker = TokenTracker()
    tracker.record(
        {"prompt_tokens": 1000, "completion_tokens": 200, "cached_tokens": 600},
        model_name="vendor/model-a",
        duration_ms=1200.0,
        ttft_ms=300.0,
        cost_usd=0.0123,
        cache_savings_usd=0.004,
    )
    metrics = TaskMetrics(task_id="demo")
    metrics.record_compression(tokens_saved=4000)

    summary = SessionSummary(
        total_events=9,
        tool_call_count=3,
        error_count=2,
        compaction_count=1,
        duration_ms=1500,
        runtime_skills=5,
        runtime_tools=7,
    )
    summary.token_economics = tracker.to_dict()
    summary.task_metrics = metrics.to_dict()
    return generate_cli_summary("demo", summary.to_dict())


@pytest.mark.parametrize(
    "line",
    [
        " Total Duration:  1.50s",
        " Total Events:    9",
        " Tool Calls:      3",
        " Errors:          2",
        " Runtime Skills:  5",
        " Runtime Tools:   7",
        "   Cost (USD):    $0.0123",
        "   Cache Savings: $0.0040",
        "   Input Tokens:  1000",
        "   Output Tokens: 200",
        "   Cached Tokens: 600",
        "   Avg TTFT:      300ms",
        "   Compactions:   1",
        "   Saved Tokens:  4000",
    ],
)
def test_the_summary_prints_the_figure_the_session_exports(printed: str, line: str) -> None:
    assert line in printed.splitlines()


def test_the_model_breakdown_names_the_model_with_its_cost(printed: str) -> None:
    row = next(line for line in printed.splitlines() if line.strip().startswith("model-a"))

    assert "$0.0123" in row
