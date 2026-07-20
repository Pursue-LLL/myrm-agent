"""Cron job tools_allowed normalization and runtime intersection.

[INPUT]
- builtin_tool_ids.normalize_enabled_builtin_tools: canonical ID normalizer

[OUTPUT]
- normalize_cron_tools_allowed: Clean and validate cron job tools_allowed
- intersect_cron_enabled_builtin_tools: Runtime intersection for job execution

[POS]
Cron tools policy — restricts per-job tool access at schedule and runtime.
"""

from __future__ import annotations

from collections.abc import Sequence

from app.services.agent.builtin_tool_ids import normalize_enabled_builtin_tools


def normalize_cron_tools_allowed(tools: Sequence[str] | None) -> tuple[str, ...] | None:
    """Validate cron job tools_allowed; empty input means no restriction."""
    if tools is None:
        return None
    cleaned = [str(t).strip() for t in tools if str(t).strip()]
    if not cleaned:
        return None
    normalized = normalize_enabled_builtin_tools(cleaned)
    filtered = tuple(t for t in normalized if t != "cron")
    return filtered or None


def intersect_cron_enabled_builtin_tools(
    agent_tools: Sequence[str],
    job_tools_allowed: tuple[str, ...] | None,
) -> list[str]:
    """Intersect agent profile tools with optional per-job tools_allowed."""
    effective = [tool_id for tool_id in agent_tools if tool_id != "cron"]
    if job_tools_allowed is None:
        return effective
    allowed = frozenset(job_tools_allowed)
    return [tool_id for tool_id in effective if tool_id in allowed]
