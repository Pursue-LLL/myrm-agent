"""CLI summary table of a finished session.

[INPUT]
- event_log.types::SessionSummary (POS: Session-level counters and token economics the logger accumulates)

[OUTPUT]
- generate_cli_summary: Generate a geek-friendly CLI summary table for a session.

[POS]
Developer-facing text rendering of ``SessionSummary``; printed by ``EventLogger.close``.
"""

from __future__ import annotations

from typing import cast

from .types import SessionSummary

_RULE = "-" * 60
_DOUBLE_RULE = "=" * 60


def generate_cli_summary(session_id: str, summary: SessionSummary) -> str:
    """Generate a geek-friendly CLI summary table for a session."""

    lines = [_DOUBLE_RULE, f" SESSION SUMMARY: {session_id}", _DOUBLE_RULE]

    # 1. Execution Overview
    lines.append(f" Total Duration:  {summary.duration_ms / 1000.0:.2f}s")
    lines.append(f" Total Events:    {summary.total_events}")
    lines.append(f" Tool Calls:      {summary.tool_call_count}")
    lines.append(f" Errors:          {summary.error_count}")

    if summary.runtime_skills is not None or summary.runtime_tools is not None:
        lines.append(f" Runtime Skills:  {summary.runtime_skills or 0}")
        lines.append(f" Runtime Tools:   {summary.runtime_tools or 0}")

    lines.append(_RULE)

    # 2. Token Economics
    token_eco = summary.token_economics
    if token_eco:
        usage = _as_section(token_eco.get("usage"))
        latency = _as_section(token_eco.get("latency"))

        lines.append(" TOKEN ECONOMICS")
        lines.append(f"   Cost (USD):    ${_number(token_eco, 'total_cost_usd'):.4f}")
        savings = _number(token_eco, "total_cache_savings_usd")
        if savings > 0:
            lines.append(f"   Cache Savings: ${savings:.4f}")

        lines.append(f"   Input Tokens:  {_number(usage, 'prompt_tokens')}")
        lines.append(f"   Output Tokens: {_number(usage, 'completion_tokens')}")
        lines.append(f"   Cached Tokens: {_number(usage, 'cached_tokens')}")

        lines.append(" LATENCY METRICS")
        lines.append(f"   Avg TTFT:      {_number(latency, 'avg_ttft_ms'):.0f}ms")
        lines.append(f"   P95 Latency:   {_number(latency, 'p95_ms'):.0f}ms")
        lines.append(f"   Tokens/Sec:    {_number(latency, 'avg_tokens_per_second'):.1f}")
        lines.append(_RULE)

        # 3. Model Breakdown
        model_bd = _as_section(token_eco.get("model_breakdown"))
        if model_bd:
            lines.append(" MODEL BREAKDOWN")
            lines.append(f"   {'Model':<30} | {'Tokens':<10} | {'Cost':<10}")
            lines.append(f"   {'-' * 30}-+-{'-' * 10}-+-{'-' * 10}")
            for model, entry in model_bd.items():
                data = _as_section(entry)
                short_model = model.split("/")[-1][:30]
                tokens = _number(data, "total_tokens")
                cost = f"${_number(data, 'cost_usd'):.4f}"
                lines.append(f"   {short_model:<30} | {tokens:<10} | {cost:<10}")
            lines.append(_RULE)

    # 4. Task Metrics (Context Compaction)
    task_metrics = summary.task_metrics
    if task_metrics:
        lines.append(" CONTEXT METRICS")
        lines.append(f"   Compactions:   {_number(task_metrics, 'compression_count')}")
        lines.append(f"   Saved Tokens:  {_number(task_metrics, 'total_tokens_saved')}")
        lines.append(_RULE)

    lines.append(_DOUBLE_RULE)

    return "\n".join(lines)


def _as_section(value: object) -> dict[str, object]:
    """``value`` when it is a mapping, else an empty one: a missing section prints as zeros."""
    return cast("dict[str, object]", value) if isinstance(value, dict) else {}


def _number(section: dict[str, object], key: str) -> float:
    value = section.get(key)
    return value if isinstance(value, int | float) else 0
