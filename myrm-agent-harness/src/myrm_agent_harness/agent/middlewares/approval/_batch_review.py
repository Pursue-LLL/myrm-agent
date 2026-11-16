"""Batch review helpers — LLM review and runtime domain tracking.

[INPUT]
- agent.security.types::RecentToolCall, ReviewResult, SecurityReviewerProtocol (POS: Security type definitions — re-exported from core.security.types.)

[OUTPUT]
- register_security_reviewer: Register or unregister a Transcript Classifier.
- reset_runtime_domains: Reset runtime-approved domains.
- _run_llm_review: Execute Transcript Classifier with fail-safe handling.
- _get_runtime_domains: Return session-scoped runtime-approved domains.
- _truncate_tool_args: Truncate large string values in tool arguments.

[POS]
Batch review helpers — LLM review and runtime domain tracking.
"""

from __future__ import annotations

import logging
from contextvars import ContextVar

from myrm_agent_harness.agent.security.types import (
    RecentToolCall,
    ReviewResult,
    SecurityReviewerProtocol,
)

logger = logging.getLogger(__name__)

__all__ = [
    "_get_runtime_domains",
    "_run_llm_review",
    "_truncate_tool_args",
    "register_security_reviewer",
    "reset_runtime_domains",
]

_runtime_allowed_domains: ContextVar[set[str]] = ContextVar("runtime_allowed_domains")

_security_reviewer: SecurityReviewerProtocol | None = None


def _truncate_tool_args(tool_input: dict[str, object], max_chars: int = 1000) -> dict[str, object]:
    """Truncate large string values in tool arguments to prevent prompt explosion."""
    result: dict[str, object] = {}
    for k, v in tool_input.items():
        if isinstance(v, str) and len(v) > max_chars:
            result[k] = v[:max_chars] + f"... [truncated {len(v) - max_chars} chars]"
        else:
            result[k] = v
    return result


def register_security_reviewer(reviewer: SecurityReviewerProtocol | None) -> None:
    """Register or unregister an LLM security reviewer for auto-mode.

    Called by the business layer during agent initialization. When None,
    the Transcript Classifier is disabled regardless of ``auto_mode_enabled``.
    """
    global _security_reviewer
    _security_reviewer = reviewer


async def _run_llm_review(
    command: str,
    workspace_root: str | None,
    intent_context: str | None = None,
    taint_labels: frozenset[str] | None = None,
    recent_tool_calls: tuple[RecentToolCall, ...] = (),
    model_id: str | None = None,
    trusted_domains: tuple[str, ...] = (),
) -> ReviewResult | None:
    """Execute Transcript Classifier with fail-safe error handling.

    Returns None on any failure (treated as UNCERTAIN -> falls through to HITL).
    """
    reviewer = _security_reviewer
    if reviewer is None:
        return None
    try:
        return await reviewer.review(
            command,
            workspace_root=workspace_root,
            intent_context=intent_context,
            taint_labels=taint_labels,
            recent_tool_calls=recent_tool_calls,
            model_id=model_id,
            trusted_domains=trusted_domains,
        )
    except Exception:
        logger.warning("Transcript classifier failed, falling back to HITL", exc_info=True)
        return None


def _get_runtime_domains() -> set[str]:
    """Return the session-scoped set of runtime-approved domains."""
    try:
        return _runtime_allowed_domains.get()
    except LookupError:
        domains: set[str] = set()
        _runtime_allowed_domains.set(domains)
        return domains


def reset_runtime_domains() -> None:
    """Reset runtime-approved domains (call at session start)."""
    _runtime_allowed_domains.set(set())
