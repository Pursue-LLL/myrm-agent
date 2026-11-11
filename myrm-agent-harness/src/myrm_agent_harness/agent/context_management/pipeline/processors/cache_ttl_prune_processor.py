"""Cache-TTL context pruning processor.

When prompt cache TTL expires, old tool results no longer benefit from caching.
This processor trims or archives them using pure rule-based logic (zero API cost),
reducing input_tokens while preserving recoverability through context offload.

Position in Pipeline: after FilterProcessor, before CompressProcessor.
This creates a complete cache lifecycle:
  - cache hot → CompressProcessor bypasses (protect cache)
  - cache cold → CacheTtlPruneProcessor trims/archives (release wasted tokens)
  - still over threshold → CompressProcessor compresses (normal flow)

[INPUT]
- infra.schemas::CacheTtlPruneConfig, ContextCompressOffloadCallback
- infra.schemas::CacheUsageFeedback
- utils.token_estimation::estimate_content_tokens, estimate_message_tokens
- processors.cache_ttl_prune_helpers::* (POS: Cache TTL pruning helper layer. Keeps the processor focused on when to prune and which tool results to prune.)
- processors.cache_ttl_prune_archive::ToolResultArchiver (POS: Offloads a pruned tool result once and builds the reference that replaces it)
- processors.cache_ttl_prune_roi::effective_prune_policy, record_prune_metrics (POS: ROI ledger and backoff of the passes)

[OUTPUT]
- CacheTtlPruneProcessor: class — Cache TTL Prune Processor with optional async archive-summary checkpoints

[POS]
Provides CacheTtlPruneProcessor for token-aware, structure-aware, restore-cost-aware,
restore-contract-backed pruning of expired tool results with scoped offload idempotency.
"""

import time
from collections.abc import Mapping, Sequence
from typing import cast

from langchain_core.messages import BaseMessage, ToolMessage
from langchain_core.runnables.config import RunnableConfig

from myrm_agent_harness.utils.logger_utils import get_agent_logger
from myrm_agent_harness.utils.token_estimation import (
    estimate_content_tokens,
    estimate_message_tokens,
)

from ...archive_checkpoint import ArchiveSummaryService
from ...infra.cache_break_detector import get_cache_break_detector
from ...infra.context_budget import resolve_budget_kwargs_from_metadata
from ...infra.schemas import (
    DEFAULT_CACHE_TTL_PRUNE_CONFIG,
    TOOL_PROTECTION_CONFIG,
    CacheTtlPruneConfig,
    CacheUsageFeedback,
    ContextCompressOffloadCallback,
    ToolProtectionConfig,
)
from ..base import BaseProcessor, ProcessorContext
from .cache_ttl_prune_archive import ToolResultArchiver
from .cache_ttl_prune_helpers import (
    EffectivePrunePolicy,
    PruneStats,
    archive_budget_decision,
    content_to_text,
    find_assistant_cutoff,
    find_first_human_index,
    replace_tool_content,
    soft_trim_content,
)
from .cache_ttl_prune_roi import effective_prune_policy, record_prune_metrics

logger = get_agent_logger(__name__)

_EffectivePrunePolicy = EffectivePrunePolicy
_PruneStats = PruneStats
_content_to_text = content_to_text
_find_assistant_cutoff = find_assistant_cutoff
_find_first_human_index = find_first_human_index
_replace_tool_content = replace_tool_content
_soft_trim_content = soft_trim_content

_CACHE_FEEDBACK_MIN_CALLS = 2
_CACHE_FEEDBACK_MIN_INPUT_TOKENS = 4_000
_CACHE_FEEDBACK_HOT_HIT_RATE = 0.35
_CACHE_FEEDBACK_COLD_HIT_RATE = 0.12


class CacheTtlPruneProcessor(BaseProcessor):
    """Rule-based pruning of tool results whose prompt cache has expired.

    Two-level progressive strategy:
    - Level 1 (soft trim): ratio >= soft_trim_ratio → head+tail preservation
    - Level 2 (archive): ratio >= hard_clear_ratio → offload full result, then replace
      with a restorable placeholder. If offload is unavailable or fails, falls back
      to soft trim and never discards the original content irreversibly.

    Protection:
    - Last N assistant turns are never pruned
    - Protected tools (TOOL_PROTECTION_CONFIG) are never pruned
    - Messages before the first HumanMessage are never pruned (init reads)
    """

    def __init__(
        self,
        config: CacheTtlPruneConfig | None = None,
        protection_config: ToolProtectionConfig | None = None,
        max_context_tokens: int = 128000,
        on_prune_offload: ContextCompressOffloadCallback | None = None,
        archive_summary_service: ArchiveSummaryService | None = None,
    ):
        self._config = config or DEFAULT_CACHE_TTL_PRUNE_CONFIG
        self._protection = protection_config or TOOL_PROTECTION_CONFIG
        self._max_context_tokens = max_context_tokens
        self._archive_summary_service = archive_summary_service
        self._archiver = ToolResultArchiver(
            on_prune_offload,
            estimate_tokens=self._estimate_content_tokens_for_pruning,
            on_stored=self._dispatch_archive_summary,
        )

    @property
    def name(self) -> str:
        return "cache_ttl_prune"

    def _is_cache_expired(self, context: ProcessorContext) -> bool:
        """Determine if prompt cache has likely expired."""
        feedback = CacheUsageFeedback.from_mapping(context.metadata.get("cache_usage_feedback"))
        feedback_decision = self._cache_feedback_expired(feedback)
        if feedback_decision is not None:
            return feedback_decision

        detector = get_cache_break_detector()
        if detector is not None:
            elapsed = detector.seconds_since_last_call()
            if elapsed is not None:
                return elapsed > self._config.ttl_seconds

        last_active = context.metadata.get("last_activity_time")
        if isinstance(last_active, (int, float)):
            return (time.time() - last_active) > self._config.ttl_seconds

        return False

    def _cache_feedback_expired(self, feedback: CacheUsageFeedback | None) -> bool | None:
        """Use provider usage feedback when the business layer supplies it."""
        if feedback is None:
            return None

        if feedback.cached_tokens > 0 and feedback.cache_hit_rate >= _CACHE_FEEDBACK_HOT_HIT_RATE:
            return False

        if (
            feedback.has_stable_sample(
                min_calls=_CACHE_FEEDBACK_MIN_CALLS,
                min_input_tokens=_CACHE_FEEDBACK_MIN_INPUT_TOKENS,
            )
            and feedback.cache_hit_rate < _CACHE_FEEDBACK_COLD_HIT_RATE
        ):
            return True

        return None

    def _is_large_payload(self, content: object) -> bool:
        return (
            isinstance(content, str)
            and self._config.large_payload_fast_guard_chars > 0
            and len(content) > self._config.large_payload_fast_guard_chars
        )

    def _estimate_content_tokens_for_pruning(self, content: str | Sequence[object]) -> int:
        """Estimate payload tokens without running tokenizer on very large tool output."""
        if self._is_large_payload(content):
            return max(1, int(len(content) / 3.5))
        return estimate_content_tokens(content)

    def _estimate_message_tokens_for_pruning(self, msg: BaseMessage) -> int:
        """Estimate message tokens while protecting the prune pass from huge single payloads."""
        if not self._is_large_payload(msg.content):
            return estimate_message_tokens(msg)

        total = self._estimate_content_tokens_for_pruning(msg.content) + 4
        if isinstance(msg, ToolMessage):
            if msg.tool_call_id:
                total += max(1, int(len(msg.tool_call_id) / 3.5))
            if msg.name:
                total += max(1, int(len(msg.name) / 3.5))
        return total

    def _estimate_messages_tokens_for_pruning(self, messages: list[BaseMessage]) -> int:
        return sum(self._estimate_message_tokens_for_pruning(msg) for msg in messages)

    def _estimate_content_bytes_for_budget(self, content: str) -> int:
        """Return exact bytes for normal payloads and allocation-free estimates for huge ones."""
        if not self._is_large_payload(content):
            return len(content.encode("utf-8"))
        if content.isascii():
            return len(content)
        return len(content) * 4

    def _estimate_context_ratio(
        self,
        messages: list[BaseMessage],
        metadata: Mapping[str, object],
    ) -> float:
        """Estimate context usage as a ratio of the context window (messages + bind-tools + API max)."""
        total_tokens = self._estimate_messages_tokens_for_pruning(messages)
        budget_kwargs = resolve_budget_kwargs_from_metadata(metadata)
        total_tokens += budget_kwargs.get("bound_tool_overhead_tokens", 0)
        last_provider = budget_kwargs.get("last_provider_prompt_tokens")
        if last_provider is not None and last_provider > total_tokens:
            total_tokens = last_provider
        return total_tokens / self._max_context_tokens if self._max_context_tokens > 0 else 0.0

    def _is_emergency_prune(self, context: ProcessorContext) -> bool:
        """Allow bounded pruning when cache preservation would otherwise exceed the context window."""
        if self._config.emergency_prune_ratio <= 0:
            return False
        return self._estimate_context_ratio(context.messages, context.metadata) >= self._config.emergency_prune_ratio

    def _effective_policy(self, context: ProcessorContext) -> _EffectivePrunePolicy:
        """The thresholds of this decision: the configured ones, raised while earlier prunes did not pay off."""
        return effective_prune_policy(self._config, context.chat_id)

    async def should_process(self, context: ProcessorContext) -> bool:
        emergency_prune = self._is_emergency_prune(context)
        if self._should_skip_for_cache_preservation(context) and not emergency_prune:
            return False

        if not emergency_prune and not self._is_cache_expired(context):
            return False

        policy = self._effective_policy(context)
        ratio = self._estimate_context_ratio(context.messages, context.metadata)
        if ratio < policy.soft_trim_ratio:
            return False

        first_human = _find_first_human_index(context.messages)
        cutoff = _find_assistant_cutoff(context.messages, self._config.keep_last_assistant_turns)
        prune_start = first_human if first_human is not None else len(context.messages)

        prunable_tokens = 0
        for i in range(prune_start, cutoff):
            msg = context.messages[i]
            if not isinstance(msg, ToolMessage):
                continue
            tool_name = msg.name or "unknown"
            if self._protection.prune_mode(tool_name) == "protect":
                continue
            prunable_tokens += self._estimate_message_tokens_for_pruning(msg)

        return prunable_tokens >= policy.min_prunable_tokens

    async def process(self, context: ProcessorContext) -> ProcessorContext:
        if self._should_skip_for_cache_preservation(context) and not self._is_emergency_prune(context):
            return context

        messages = list(context.messages)
        context_messages = context.messages
        ratio = self._estimate_context_ratio(messages, context.metadata)
        policy = self._effective_policy(context)

        first_human = _find_first_human_index(messages)
        cutoff = _find_assistant_cutoff(messages, self._config.keep_last_assistant_turns)
        prune_start = first_human if first_human is not None else len(messages)

        before_tokens = self._estimate_messages_tokens_for_pruning(context_messages)
        stats = _PruneStats()
        started_at = time.perf_counter()
        offload_bytes_used = 0

        for i in range(prune_start, cutoff):
            if self._config.max_prune_wall_ms > 0:
                elapsed_ms = (time.perf_counter() - started_at) * 1000
                if elapsed_ms >= self._config.max_prune_wall_ms:
                    stats.record_deferred("wall_time_budget")
                    break

            msg = messages[i]
            if not isinstance(msg, ToolMessage):
                continue
            tool_name = msg.name or "unknown"
            prune_mode = self._protection.prune_mode(tool_name)
            if prune_mode == "protect":
                continue

            if not isinstance(msg.content, (str, list)):
                continue

            content = _content_to_text(msg.content)
            if not content:
                continue

            archive_deferred_reason = ""
            if prune_mode == "allow" and ratio >= policy.hard_clear_ratio:
                content_bytes = self._estimate_content_bytes_for_budget(content)
                budget_decision = archive_budget_decision(
                    self._config,
                    stats=stats,
                    offload_bytes_used=offload_bytes_used,
                    content_bytes=content_bytes,
                    started_at=started_at,
                )
                if budget_decision.allowed:
                    archive_attempt = await self._archiver.try_archive(
                        msg=msg,
                        content=content,
                        context=context,
                    )
                    if archive_attempt.archived:
                        messages[i] = _replace_tool_content(
                            msg,
                            archive_attempt.replacement_content,
                        )
                        stats.archived += 1
                        if archive_attempt.offload_reused:
                            stats.archive_reused += 1
                            stats.archive_bytes_reused += archive_attempt.stored_bytes or content_bytes
                        else:
                            stats.archive_written += 1
                            stats.archive_bytes_written += archive_attempt.stored_bytes or content_bytes
                            offload_bytes_used += content_bytes
                        stats.original_tokens += self._estimate_content_tokens_for_pruning(content)
                        ratio = self._estimate_context_ratio(messages, context.metadata)
                        continue

                    stats.record_offload_failure(archive_attempt.failure_kind or "temporary_failure")
                else:
                    archive_deferred_reason = budget_decision.reason
                    stats.record_archive_deferred(archive_deferred_reason)

            trimmed = self._soft_trim_replacement(content)
            if ratio >= policy.soft_trim_ratio and trimmed is not None:
                messages[i] = _replace_tool_content(msg, trimmed)
                stats.soft_trimmed += 1
                stats.original_tokens += self._estimate_content_tokens_for_pruning(content)
                if archive_deferred_reason:
                    stats.record_archive_deferred_soft_trimmed(archive_deferred_reason)
                ratio = self._estimate_context_ratio(messages, context.metadata)
            elif archive_deferred_reason:
                stats.record_deferred(archive_deferred_reason)

        if stats.soft_trimmed > 0 or stats.archived > 0:
            after_tokens = self._estimate_messages_tokens_for_pruning(messages)
            tokens_saved = max(0, before_tokens - after_tokens)
            context.messages = messages
            context.tokens_saved += tokens_saved
            prune_elapsed_ms = int((time.perf_counter() - started_at) * 1000)
            record_prune_metrics(context.chat_id, tokens_saved, stats, policy, elapsed_ms=prune_elapsed_ms)
            detector = get_cache_break_detector()
            if detector is not None:
                detector.notify_compaction()
            logger.warning(
                "[CacheTtlPrune] soft_trimmed=%d, archived=%d, offload_failed=%d, archive_deferred=%d, %d tokens saved",
                stats.soft_trimmed,
                stats.archived,
                stats.offload_failed,
                stats.archive_deferred,
                tokens_saved,
            )
        elif stats.deferred > 0 or stats.offload_failed > 0 or stats.archive_deferred > 0:
            prune_elapsed_ms = int((time.perf_counter() - started_at) * 1000)
            record_prune_metrics(context.chat_id, 0, stats, policy, elapsed_ms=prune_elapsed_ms)

        return context

    def _dispatch_archive_summary(
        self,
        msg: ToolMessage,
        content: str,
        archive_path: str,
        context: ProcessorContext,
    ) -> None:
        """Queue a background summary of a tool result that was just archived."""
        if self._archive_summary_service is not None:
            # RunnableConfig is a TypedDict, which isinstance() rejects; a plain dict is its runtime form.
            runnable_config = context.metadata.get("runnable_config")
            config = cast(RunnableConfig, runnable_config) if isinstance(runnable_config, dict) else None
            self._archive_summary_service.dispatch(
                tool_name=msg.name or "unknown",
                content=content,
                archive_path=archive_path,
                chat_id=context.chat_id,
                summarizer_llm=context.summarizer_llm or context.llm,
                tool_call_id=getattr(msg, "tool_call_id", None),
                runnable_config=config,
            )

    def _soft_trim_replacement(self, content: str) -> str | None:
        """Build a soft-trimmed replacement without mutating the source message."""
        trimmed = _soft_trim_content(content, self._config)
        return trimmed
