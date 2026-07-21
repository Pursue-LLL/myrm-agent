"""Cron job tools_allowed normalization and runtime intersection.

[INPUT]
- builtin_tool_ids.BUILTIN_TOOL_ID_SET / AGENT_BASELINE_BUILTIN_TOOLS: canonical ID catalog

[OUTPUT]
- normalize_cron_tools_allowed: Clean and validate cron job tools_allowed
- intersect_cron_enabled_builtin_tools: Runtime intersection for job execution

[POS]
Cron tools policy — restricts per-job tool access at schedule and runtime.
"""

from __future__ import annotations

from collections.abc import Sequence

from app.services.agent.builtin_tool_ids import (
    AGENT_BASELINE_BUILTIN_TOOLS,
    BUILTIN_TOOL_ID_SET,
    InvalidBuiltinToolIdsError,
    LEGACY_REJECTED_BUILTIN_TOOL_IDS,
)


def normalize_cron_tools_allowed(tools: Sequence[str] | None) -> tuple[str, ...] | None:
    """Validate cron job tools_allowed; empty input means no restriction.

    Unlike agent profile normalization, baseline tools (``file_ops``, ``code_execute``)
    are kept when explicitly listed — they express execution scope for cron jobs.
    """
    if tools is None:
        return None
    cleaned = [str(t).strip() for t in tools if str(t).strip()]
    if not cleaned:
        return None

    normalized: list[str] = []
    seen: set[str] = set()
    invalid: list[str] = []
    legacy: list[str] = []

    for tool_id in cleaned:
        if tool_id == "cron":
            continue
        if tool_id in LEGACY_REJECTED_BUILTIN_TOOL_IDS:
            legacy.append(tool_id)
            continue
        if tool_id not in BUILTIN_TOOL_ID_SET:
            invalid.append(tool_id)
            continue
        if tool_id in seen:
            continue
        seen.add(tool_id)
        normalized.append(tool_id)

    if legacy or invalid:
        parts: list[str] = []
        if legacy:
            parts.append(f"legacy IDs are no longer accepted: {sorted(set(legacy))}")
        if invalid:
            parts.append(
                f"unknown IDs: {sorted(set(invalid))}; valid: {sorted(BUILTIN_TOOL_ID_SET)}"
            )
        raise InvalidBuiltinToolIdsError("; ".join(parts))

    return tuple(normalized) if normalized else None


def intersect_cron_enabled_builtin_tools(
    agent_tools: Sequence[str],
    job_tools_allowed: tuple[str, ...] | None,
) -> list[str]:
    """Intersect agent profile tools with optional per-job tools_allowed."""
    effective = [tool_id for tool_id in agent_tools if tool_id != "cron"]
    if job_tools_allowed is None:
        return effective

    allowed = frozenset(job_tools_allowed)
    candidates = list(effective)
    for baseline in AGENT_BASELINE_BUILTIN_TOOLS:
        if baseline in allowed and baseline not in candidates:
            candidates.append(baseline)

    return [tool_id for tool_id in candidates if tool_id in allowed]
