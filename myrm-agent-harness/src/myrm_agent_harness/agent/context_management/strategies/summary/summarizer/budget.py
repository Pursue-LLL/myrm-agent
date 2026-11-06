"""摘要预算提示与结果裁剪。

[POS]
摘要策略子包的一部分；由 __init__.py 聚合导出。
"""

from __future__ import annotations

from langchain_core.messages import BaseMessage

from myrm_agent_harness.utils.logger_utils import get_agent_logger
from myrm_agent_harness.utils.token_estimation import (
    estimate_messages_tokens,
)

from ....infra.schemas import StructuredSummary
from ..summary_builder import (
    create_summary_message,
)

logger = get_agent_logger(__name__)


_SUMMARY_RATIO = 0.20
_MIN_SUMMARY_TOKENS = 2000
_MAX_SUMMARY_TOKENS = 12000


def _build_budget_hint(content_tokens: int) -> str:
    """Build a budget hint for the summary prompt.

    Allocates 20% of compressed content as budget, clamped to [2000, 12000] tokens.
    """
    budget = max(
        _MIN_SUMMARY_TOKENS,
        min(int(content_tokens * _SUMMARY_RATIO), _MAX_SUMMARY_TOKENS),
    )
    return (
        f"\nTarget length: ~{budget} tokens. Be specific and concise — "
        f"include file paths, command outputs, error messages, and exact values. "
        f"Avoid vague descriptions."
    )


# ---------------------------------------------------------------------------
# Summary output capping (prevent summary bloat)
# ---------------------------------------------------------------------------

_CAP_MAX_ACTIONS = 5
_CAP_MAX_FINDINGS = 3
_CAP_MAX_ERRORS = 3
_CAP_GOAL_MAX_CHARS = 200


def _cap_summary_if_needed(
    summary: StructuredSummary,
    original_tokens: int,
    recent_messages: list[BaseMessage],
    chat_id: str | None,
    preserved_context: str | None = None,
) -> StructuredSummary:
    """Ensure summarised output is shorter than the original.

    Applies progressive truncation following the Lost-in-Middle principle:
    truncate middle fields first (completed_actions), preserve start
    (user_goal) and end (errors_and_fixes).
    """
    summary_message = create_summary_message(summary, chat_id, preserved_context=preserved_context)
    new_tokens = estimate_messages_tokens([summary_message, *recent_messages])

    if new_tokens < original_tokens:
        return summary

    logger.warning(
        " Summary bloat detected: %d → %d tokens, applying progressive cap",
        original_tokens,
        new_tokens,
    )

    # Phase 1: trim middle-attention fields first
    summary.completed_actions = summary.completed_actions[:_CAP_MAX_ACTIONS]
    summary.key_findings = summary.key_findings[:_CAP_MAX_FINDINGS]
    summary.errors_and_fixes = summary.errors_and_fixes[:_CAP_MAX_ERRORS]
    summary.resolved_questions = summary.resolved_questions[:3]

    summary_message = create_summary_message(summary, chat_id, preserved_context=preserved_context)
    new_tokens = estimate_messages_tokens([summary_message, *recent_messages])
    if new_tokens < original_tokens:
        return summary

    # Phase 2: aggressive trimming
    if len(summary.user_goal) > _CAP_GOAL_MAX_CHARS:
        summary.user_goal = summary.user_goal[:_CAP_GOAL_MAX_CHARS] + "…"
    summary.completed_actions = summary.completed_actions[:2]
    summary.key_findings = summary.key_findings[:1]
    summary.resolved_questions = summary.resolved_questions[:1]
    summary.constraints_and_preferences = summary.constraints_and_preferences[:2]

    logger.warning(" Applied aggressive cap to summary fields")
    return summary


# ---------------------------------------------------------------------------
# Audit + retry orchestration
# ---------------------------------------------------------------------------

_MAX_AUDIT_RETRIES = 2
