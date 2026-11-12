"""[INPUT]
- myrm_agent_harness.agent.context_management.strategies.summary.summarizer.budget::_build_budget_hint (POS: 摘要策略子包的一部分；由 __init__.py 聚合导出。)
- myrm_agent_harness.agent.context_management.strategies.summary.summarizer.guard::_guard_aux_context (POS: 摘要策略子包的一部分；由 __init__.py 聚合导出。)
- myrm_agent_harness.agent.context_management.strategies.summary.summarizer.invocation::_get_structured_llm_or_parser / _invoke_summary / _redact_summary_fields (POS: 摘要策略子包的一部分；由 __init__.py 聚合导出。)
- myrm_agent_harness.utils.logger_utils::get_agent_logger (POS: Unified logging utilities. Provides consistent log format and convenience methods (step/success/error_detail) for project-wide log output.)
- myrm_agent_harness.utils.token_estimation::estimate_messages_tokens (POS: Token estimation infrastructure. Covers message-level tokens and bind-tools overhead for context budget / compress / summarize decisions.)
- myrm_agent_harness.agent.context_management.infra.schemas::StructuredSummary (POS: Context management shared data structures. Defines compact format types, summary schemas, and configuration constants as)
- myrm_agent_harness.agent.context_management.strategies.summary.exact_anchor::ExactAnchorTable (POS: Harness framework layer context management. Extracts verbatim machine symbols (Git commit SHAs, file paths, fatal stack trace spans, code symbols, API routes) before context compaction.)
- myrm_agent_harness.agent.context_management.strategies.summary.progress_timeout::SummaryProgressTracker (POS: Progress-aware timeout primitives for summarization. Decouples timeout detection from LLM invocation, allowing watchdog coroutines to observe liveness without coupling to specific streaming implementations.)
- myrm_agent_harness.agent.context_management.strategies.summary.summary_parser::format_messages_for_summary (POS: Summary parsing and message formatting utilities.)
- myrm_agent_harness.agent.context_management.strategies.summary.summary_prompts::FOCUS_TOPIC_SUFFIX / SPLIT_TURN_PROMPT_SUFFIX / SUMMARY_MERGE_PROMPT_TEMPLATE / SUMMARY_PROMPT_TEMPLATE (POS: Summarization prompt templates. Defines structured JSON output format (with Handoff fields) and merge rules for `summarizer/`.)

[OUTPUT]
- _summarize_full_with_audit: Generate a full summary with quality audit and retry.
- _summarize_incremental_with_audit: Generate an incremental summary with quality audit and retry.
- _log_merge_quality: Record incremental merge quality metrics (pre/post information count).
- _record_summarize_to_metrics: Record a summarize event to TaskMetrics.

[POS]
摘要策略子包的一部分；由 __init__.py 聚合导出。
"""

from __future__ import annotations

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage

from myrm_agent_harness.agent.context_management.strategies.summary.summarizer.budget import _build_budget_hint
from myrm_agent_harness.agent.context_management.strategies.summary.summarizer.guard import _guard_aux_context
from myrm_agent_harness.agent.context_management.strategies.summary.summarizer.invocation import (
    _get_structured_llm_or_parser,
    _invoke_summary,
    _redact_summary_fields,
)
from myrm_agent_harness.utils.logger_utils import get_agent_logger
from myrm_agent_harness.utils.token_estimation import (
    estimate_messages_tokens,
)

from ....infra.schemas import StructuredSummary
from ..exact_anchor import ExactAnchorTable
from ..progress_timeout import (
    SummaryProgressTracker,
)
from ..summary_parser import (
    format_messages_for_summary,
)
from ..summary_prompts import (
    FOCUS_TOPIC_SUFFIX,
    SPLIT_TURN_PROMPT_SUFFIX,
    SUMMARY_MERGE_PROMPT_TEMPLATE,
    SUMMARY_PROMPT_TEMPLATE,
)

logger = get_agent_logger(__name__)

_MAX_AUDIT_RETRIES = 2


async def _summarize_full_with_audit(
    llm: BaseChatModel,
    messages: list[BaseMessage],
    dump_path: str,
    entities: set[str],
    focus_topic: str = "",
    turn_prefix_messages: list[BaseMessage] | None = None,
    progress_tracker: SummaryProgressTracker | None = None,
    chat_id: str | None = None,
    exact_anchors: ExactAnchorTable | None = None,
) -> StructuredSummary:
    """Generate a full summary with quality audit and retry."""
    from ..summary_auditor import audit_summary, build_retry_guidance

    original_tokens = estimate_messages_tokens(messages)
    budget_hint = _build_budget_hint(original_tokens)

    cache_safe_base_prompt = SUMMARY_PROMPT_TEMPLATE.format(
        context="Use the preceding conversation messages as the Conversation History.",
        budget_hint=budget_hint,
    )
    if focus_topic:
        cache_safe_base_prompt += FOCUS_TOPIC_SUFFIX.format(focus_topic=focus_topic)

    if turn_prefix_messages:
        turn_prefix_text = format_messages_for_summary(turn_prefix_messages)
        cache_safe_base_prompt += SPLIT_TURN_PROMPT_SUFFIX.format(turn_prefix_text=turn_prefix_text)

    best: StructuredSummary | None = None
    best_retained = -1

    structured_llm, parser = _get_structured_llm_or_parser(llm)

    prompt_tokens = estimate_messages_tokens([HumanMessage(content=cache_safe_base_prompt)])
    guarded_messages = _guard_aux_context(messages, llm, prompt_tokens)

    for attempt in range(_MAX_AUDIT_RETRIES + 1):
        prompt = cache_safe_base_prompt
        if attempt > 0 and best is not None:
            guidance = build_retry_guidance(
                audit_summary(best, messages, entities=entities, exact_anchors=exact_anchors)
            )
            prompt = f"{cache_safe_base_prompt}\n\n Quality feedback:\n{guidance}"

        try:
            summary = await _invoke_summary(
                llm,
                structured_llm,
                parser,
                prompt,
                dump_path,
                cache_prefix_messages=guarded_messages,
                progress_tracker=progress_tracker,
            )
        except Exception as e:
            logger.warning(" Structured output failed: %s", e)
            if attempt == _MAX_AUDIT_RETRIES and best is None:
                raise ValueError(f"Failed to generate structured summary: {e}") from e
            continue

        result = audit_summary(summary, messages, entities=entities, chat_id=chat_id, exact_anchors=exact_anchors)
        if result.entity_retained > best_retained:
            best = summary
            best_retained = result.entity_retained

        if result.passed:
            logger.warning(
                " Full summary done (attempt %d): goal=%s...",
                attempt + 1,
                summary.user_goal[:50],
            )
            return summary

        logger.warning(
            " Summary audit failed (attempt %d/%d): %s",
            attempt + 1,
            _MAX_AUDIT_RETRIES + 1,
            "; ".join(result.issues),
        )

    logger.warning(
        " Using best summary after %d attempts (retained %d entities)",
        _MAX_AUDIT_RETRIES + 1,
        best_retained,
    )
    return best  # type: ignore[return-value]


async def _summarize_incremental_with_audit(
    llm: BaseChatModel,
    existing_summary: StructuredSummary,
    new_messages: list[BaseMessage],
    dump_path: str,
    all_messages: list[BaseMessage],
    entities: set[str],
    focus_topic: str = "",
    turn_prefix_messages: list[BaseMessage] | None = None,
    progress_tracker: SummaryProgressTracker | None = None,
    chat_id: str | None = None,
    exact_anchors: ExactAnchorTable | None = None,
) -> StructuredSummary:
    """Generate an incremental summary with quality audit and retry."""
    from ..summary_auditor import audit_summary, build_retry_guidance

    existing_summary = _redact_summary_fields(existing_summary)

    new_tokens = estimate_messages_tokens(new_messages)
    budget_hint = _build_budget_hint(new_tokens)

    cache_safe_base_prompt = SUMMARY_MERGE_PROMPT_TEMPLATE.format(
        existing_summary=existing_summary.to_json(),
        new_context="Use the preceding conversation messages as the New Conversation Content.",
        budget_hint=budget_hint,
    )
    if focus_topic:
        cache_safe_base_prompt += FOCUS_TOPIC_SUFFIX.format(focus_topic=focus_topic)

    if turn_prefix_messages:
        turn_prefix_text = format_messages_for_summary(turn_prefix_messages)
        cache_safe_base_prompt += SPLIT_TURN_PROMPT_SUFFIX.format(turn_prefix_text=turn_prefix_text)

    best: StructuredSummary | None = None
    best_retained = -1

    structured_llm, parser = _get_structured_llm_or_parser(llm)

    prompt_tokens = estimate_messages_tokens([HumanMessage(content=cache_safe_base_prompt)])
    guarded_new_messages = _guard_aux_context(new_messages, llm, prompt_tokens)

    for attempt in range(_MAX_AUDIT_RETRIES + 1):
        prompt = cache_safe_base_prompt
        if attempt > 0 and best is not None:
            guidance = build_retry_guidance(
                audit_summary(best, all_messages, entities=entities, chat_id=chat_id, exact_anchors=exact_anchors)
            )
            prompt = f"{cache_safe_base_prompt}\n\n Quality feedback:\n{guidance}"

        try:
            summary = await _invoke_summary(
                llm,
                structured_llm,
                parser,
                prompt,
                dump_path,
                cache_prefix_messages=guarded_new_messages,
                progress_tracker=progress_tracker,
            )
        except Exception as e:
            logger.warning(" Structured output failed: %s", e)
            if attempt == _MAX_AUDIT_RETRIES and best is None:
                raise ValueError(f"Failed to generate structured summary: {e}") from e
            continue

        result = audit_summary(summary, all_messages, entities=entities, chat_id=chat_id, exact_anchors=exact_anchors)
        if result.entity_retained > best_retained:
            best = summary
            best_retained = result.entity_retained

        if result.passed:
            _log_merge_quality(existing_summary, summary)
            logger.warning(
                " Incremental merge done (attempt %d): goal=%s...",
                attempt + 1,
                summary.user_goal[:50],
            )
            return summary

        logger.warning(
            " Incremental audit failed (attempt %d/%d): %s",
            attempt + 1,
            _MAX_AUDIT_RETRIES + 1,
            "; ".join(result.issues),
        )

    _log_merge_quality(existing_summary, best)  # type: ignore[arg-type]
    logger.warning(
        " Using best incremental summary after %d attempts (retained %d entities)",
        _MAX_AUDIT_RETRIES + 1,
        best_retained,
    )
    return best  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _log_merge_quality(before: StructuredSummary, after: StructuredSummary) -> None:
    """Record incremental merge quality metrics (pre/post information count)."""
    actions_before = len(before.completed_actions)
    actions_after = len(after.completed_actions)
    findings_before = len(before.key_findings)
    findings_after = len(after.key_findings)
    errors_before = len(before.errors_and_fixes)
    errors_after = len(after.errors_and_fixes)
    files_before = len(before.files_modified)
    files_after = len(after.files_modified)

    changes: list[str] = []
    for label, b, a in [
        ("actions", actions_before, actions_after),
        ("findings", findings_before, findings_after),
        ("errors", errors_before, errors_after),
        ("files", files_before, files_after),
    ]:
        suffix = " " if a < b else ""
        changes.append(f"{label}: {b}→{a}{suffix}")

    has_loss = (
        actions_after < actions_before
        or findings_after < findings_before
        or errors_after < errors_before
        or files_after < files_before
    )

    if has_loss:
        logger.warning(f" Incremental merge may have lost info: {', '.join(changes)}")
    else:
        logger.warning(f" Incremental merge quality: {', '.join(changes)}")


def _record_summarize_to_metrics(tokens_saved: int, details: str = "", *, elapsed_ms: int = 0) -> None:
    """Record a summarize event to TaskMetrics."""
    try:
        from myrm_agent_harness.agent.context_management.infra.session_lock import (
            get_current_chat_id,
        )
        from myrm_agent_harness.agent.context_management.tracking.task_metrics import (
            get_task_metrics,
        )

        chat_id = get_current_chat_id()
        if chat_id:
            metrics = get_task_metrics(chat_id)
            if metrics:
                metrics.record_compression(
                    tokens_saved=tokens_saved,
                    compression_type="summarize",
                    details=details,
                    elapsed_ms=elapsed_ms,
                )
    except Exception as e:
        logger.warning("[Summarize] Failed to record to TaskMetrics: %s", e)
