"""SummarizeProcessor：在会话笔记不可用时生成结构化摘要，并降级到确定性摘要。

[INPUT]
- .circuit_breaker::MAX_CONSECUTIVE_SUMMARIZE_FAILURES / _get_failures / _is_circuit_open / _is_half_open_probe / _record_fallback_call / _set_failures (POS: 熔断状态读写)
- .fallback::_build_deterministic_summary (POS: 无 LLM 的确定性摘要)
- .fallback::_extract_focus_topic (POS: 压缩意图提示)
- .guard::_guarded_summarize (POS: 带超时与取消保护的摘要调用)
- agent.context_management.infra.compactor_guard::CompactorPreflightFence (POS: 预压缩前置守卫)
- agent.context_management.infra.schemas (POS: 预算、配置与结构化摘要类型)
- agent.context_management.strategies.summary.summarizer::should_summarize (POS: 何时触发摘要)
- agent.context_management.strategies.summary.summary_builder (POS: 摘要消息构造与近期消息提取)
- utils.token_estimation::estimate_messages_tokens (POS: token 估算)

[OUTPUT]
- SummarizeProcessor: 结构化会话摘要处理器（LLM / 外部直充 / 确定性降级）

[POS]
`summarize_processor/` 的处理器实现；熔断、降级与超时保护分别在兄弟模块。
"""

from __future__ import annotations

import time

from myrm_agent_harness.observability.metrics.circuit_breaker_metrics import (
    circuit_breaker_failures_total,
    circuit_breaker_state,
)
from myrm_agent_harness.utils.logger_utils import get_agent_logger
from myrm_agent_harness.utils.token_estimation import estimate_messages_tokens

from ....infra.compactor_guard import CompactorPreflightFence
from ....infra.context_budget import (
    estimate_processor_context_tokens,
    resolve_budget_kwargs_from_metadata,
)
from ....infra.schemas import (
    CANCEL_COMPACTION_METADATA_KEY,
    PRE_COMPACT_REPLACEMENT_SUMMARY_METADATA_KEY,
    ContextCompressOffloadCallback,
    ContextConfig,
    StructuredSummary,
)
from ....strategies.summary.progress_timeout import (
    InactivityTimeoutError,
    TotalCeilingTimeoutError,
)
from ....strategies.summary.summarizer import should_summarize
from ...base import BaseProcessor, ProcessorContext
from .apply import assemble_summarized_messages
from .circuit_breaker import (
    MAX_CONSECUTIVE_SUMMARIZE_FAILURES,
    _classify_error_type,
    _cooldown_seconds,
    _get_failures,
    _is_circuit_open,
    _is_half_open_probe,
    _record_fallback_call,
    _reset_fallback_calls,
    _set_failures,
)
from .fallback import _build_deterministic_summary, _extract_focus_topic
from .guard import _guarded_summarize

logger = get_agent_logger(__name__)

# Anti-consecutive-summarize: after summarization, the local token estimate drops
# drastically but the last AIMessage's usage_metadata.input_tokens still holds the
# pre-summary high value, which would immediately re-trigger summarization.
_skip_next_api_token_check: bool = False


class SummarizeProcessor(BaseProcessor):
    """Summarize processor.

    When context exceeds threshold:
    1. Attempt LLM-generated structured summary (goal, actions, findings, files)
    2. Degrade to deterministic fallback when LLM unavailable (never fails)
    3. Replace old messages with summary + N most recent tool calls
    4. Write StructuredSummary to context.structured_summary (for persistence)

    Three-tier guarantee:
    - L1: LLM summary + output hard-truncation (summarizer.py)
    - L2: Deterministic fallback (this file)
    - L3: Emergency conversation truncation (stream_executor.py)
    """

    def __init__(
        self,
        config: ContextConfig | None = None,
        on_prune_offload: ContextCompressOffloadCallback | None = None,
    ):
        from myrm_agent_harness.agent.context_management.infra.schemas import (
            DEFAULT_CONTEXT_CONFIG,
        )

        self.config = config or DEFAULT_CONTEXT_CONFIG
        self._on_prune_offload = on_prune_offload

    @property
    def name(self) -> str:
        return "summarize"

    _HOT_CACHE_WINDOW_SECONDS: float = 300.0  # 5 minutes

    async def _emit_compaction_status(self, context: ProcessorContext, phase: str, **extra: object) -> None:
        """Emit a context_compaction status event (best-effort, never throws)."""
        from myrm_agent_harness.utils.event_utils import dispatch_custom_event

        try:
            payload: dict[str, object] = {
                "step_key": "context_compaction",
                "phase": phase,
            }
            payload.update(extra)
            runnable_config = context.metadata.get("runnable_config")
            await dispatch_custom_event("agent_status", payload, config=runnable_config)  # type: ignore[arg-type]
        except Exception:
            pass

    def _should_bypass_for_hot_cache(self, context: ProcessorContext, current_tokens: int) -> bool:
        """Check whether to bypass summarization due to hot cache."""
        max_tokens = self.config.max_context_tokens or 128000
        if current_tokens >= max_tokens * 0.90:
            return False  # MUST summarize synchronously to avoid OOM

        last_active = context.metadata.get("last_activity_time")
        return bool(
            isinstance(last_active, (int, float)) and time.time() - last_active < self._HOT_CACHE_WINDOW_SECONDS
        )

    async def should_process(self, context: ProcessorContext) -> bool:
        global _skip_next_api_token_check
        if context.metadata.get(CANCEL_COMPACTION_METADATA_KEY) is True:
            return False

        if context.metadata.get(PRE_COMPACT_REPLACEMENT_SUMMARY_METADATA_KEY) is not None:
            return True

        if context.structured_summary is not None:
            return False

        ignore_api = _skip_next_api_token_check
        if _skip_next_api_token_check:
            _skip_next_api_token_check = False

        should_sum = should_summarize(
            context.messages,
            config=self.config,
            ignore_api_tokens=ignore_api,
            **resolve_budget_kwargs_from_metadata(context.metadata),
        )
        if not should_sum:
            return False

        total_tokens = estimate_processor_context_tokens(context.messages, context.metadata)
        if self._should_bypass_for_hot_cache(context, total_tokens):
            logger.info(
                "[Summarize] Hot cache bypass (tokens=%d), marking compaction_debt_pending",
                total_tokens,
            )
            context.metadata["compaction_debt_pending"] = True
            from ....tracking.task_metrics import get_task_metrics

            if context.chat_id:
                metrics = get_task_metrics(context.chat_id)
                if metrics:
                    metrics.compaction_debt_pending = True
            return False

        logger.info(
            "[Summarize] Cold cache or hard limit reached (tokens=%d), starting summarization",
            total_tokens,
        )
        return True

    async def process(self, context: ProcessorContext) -> ProcessorContext:
        if context.metadata.get(CANCEL_COMPACTION_METADATA_KEY) is True:
            return context

        replacement = context.metadata.get(PRE_COMPACT_REPLACEMENT_SUMMARY_METADATA_KEY)
        if isinstance(replacement, StructuredSummary):
            original_tokens = estimate_messages_tokens(context.messages)
            last_msg_db_id = context.metadata.get("last_message_db_id")
            return self._apply_structured_summary(context, replacement, original_tokens, last_msg_db_id)

        # Prompt Cache preservation: Skip summarize during Resume or HITL session
        if self._should_skip_for_cache_preservation(context):
            logger.info(
                "[Summarize] Skipped for Prompt Cache preservation (is_resume=%s, hitl_session_active=%s)",
                context.is_resume,
                context.merged_context.get("hitl_session_active"),
            )
            return context

        # Pre-compaction deterministic transient eviction & tool-result pruning
        from ....strategies.compactor.selective_eviction import evict_messages_by_marks

        evicted_msgs, evict_stats = evict_messages_by_marks(context.messages)
        if evict_stats.evicted_count > 0:
            context.messages = evicted_msgs
            context.tokens_saved += evict_stats.tokens_saved
            context.operations.append(
                f"pre_summarize_eviction: pruned {evict_stats.evicted_count} transient messages "
                f"(marks={evict_stats.evicted_marks}, saved ~{evict_stats.tokens_saved} tokens)"
            )

        if context.metadata.get("enable_pre_compact_tool_prune", True):
            from ..active_tool_result_prune_processor import prune_tool_results_deterministic

            pre_prune_thresh = int(context.metadata.get("pre_compact_prune_threshold_tokens", 1024))
            raw_keep = int(context.metadata.get("pre_compact_keep_recent_calls", 2))
            # Hard boundary guard against Goodhart's Law: never discard last 2 tool interactions
            pre_prune_keep = max(raw_keep, 2)
            effective_offload = context.metadata.get("on_prune_offload", self._on_prune_offload)

            new_msgs, pruned_cnt, saved_tokens = await prune_tool_results_deterministic(
                context.messages,
                threshold_tokens=pre_prune_thresh,
                keep_recent_calls=pre_prune_keep,
                min_reclaim_tokens=0,
                enable_memory_fallback=True,
                on_prune_offload=effective_offload,
                chat_id=context.chat_id,
                force=True,
                reason="summarize_short_circuit",
            )

            if pruned_cnt > 0 and saved_tokens > 0:
                context.messages = new_msgs
                context.tokens_saved += saved_tokens
                context.operations.append(
                    f"pre_compact_prune: pruned {pruned_cnt} tool results, saved ~{saved_tokens} tokens"
                )

                # Remeasure context tokens with safety headroom (10% measurement decay guard)
                remeasured_tokens = estimate_processor_context_tokens(context.messages, context.metadata)
                trigger_thresh = getattr(self.config, "summarize_trigger_threshold", 115200)
                # Keep 10% safety headroom: must be comfortably below trigger threshold to bypass
                safe_ceiling = int(trigger_thresh * 0.90)

                if remeasured_tokens <= safe_ceiling:
                    logger.info(
                        "[Summarize] Pre-compaction deterministic pruning short-circuit: "
                        "saved %d tokens (current=%d <= safe_ceiling=%d). Completely bypassed LLM summarization!",
                        saved_tokens,
                        remeasured_tokens,
                        safe_ceiling,
                    )
                    context.metadata["deterministic_prune_bypassed_summarize"] = True
                    context.metadata.pop("compaction_debt_pending", None)
                    from ....tracking.task_metrics import get_task_metrics

                    if context.chat_id:
                        metrics = get_task_metrics(context.chat_id)
                        if metrics:
                            metrics.compaction_debt_pending = False
                    return context

        original_tokens = estimate_messages_tokens(context.messages)
        last_msg_db_id = context.metadata.get("last_message_db_id")
        circuit_open = _is_circuit_open()

        summarize_llm = context.summarizer_llm or context.llm
        if summarize_llm is None or (circuit_open and not _is_half_open_probe()):
            reason = "circuit breaker tripped" if circuit_open else "no LLM client"
            logger.warning("[Summarize] %s — using deterministic fallback", reason)
            _record_fallback_call()
            await self._emit_compaction_status(context, "circuit_open", reason=reason)
            return self._apply_deterministic_fallback(context, original_tokens, last_msg_db_id)

        if circuit_open:
            logger.info("[Summarize] half-open probe — attempting LLM recovery")

        focus_topic = _extract_focus_topic(context.metadata)

        from ....strategies.compactor.pre_compact_context import get_pre_compact_message

        pre_compact_message = get_pre_compact_message(context)

        runnable_config = context.metadata.get("runnable_config")

        fence = CompactorPreflightFence(safe_watermark_ratio=0.85)
        # Physical model capacity limit: defaults to 128k tokens (or higher if configured),
        # distinguishing between logical conversation threshold and physical LLM window.
        max_ctx = int(
            context.metadata.get("llm_max_context_tokens")
            or getattr(self.config, "llm_max_context_tokens", None)
            or max(self.config.max_context_tokens or 128_000, 128_000)
        )
        skills_tokens = int(context.metadata.get("loaded_skills_tokens") or 0)
        safety_verdict = fence.evaluate_safety(
            messages_tokens=original_tokens,
            loaded_skills_tokens=skills_tokens,
            prompt_overhead=1000,
            max_context_tokens=max_ctx,
        )

        if not safety_verdict.is_safe:
            logger.warning(
                "[Summarize] Preflight safety fence tripped: payload tokens %d exceeds safe watermark "
                "(ratio %.2f of %d, action=%s) — bypassing LLM to avoid ContextLengthExceeded",
                safety_verdict.total_estimated_tokens,
                safety_verdict.utilization_ratio,
                safety_verdict.max_context_tokens,
                safety_verdict.action_recommended,
            )
            await self._emit_compaction_status(context, "fallback", reason="preflight_fence_overflow")
            return self._apply_deterministic_fallback(context, original_tokens, last_msg_db_id)

        try:
            context.messages, summary = await _guarded_summarize(
                messages=context.messages,
                llm=summarize_llm,
                chat_id=context.chat_id,
                config=self.config,
                focus_topic=focus_topic,
                pre_compact_message=pre_compact_message,
                runnable_config=runnable_config,
            )
        except (InactivityTimeoutError, TotalCeilingTimeoutError) as timeout_exc:
            prev = _get_failures()
            _set_failures(prev + 1, "transient")
            _record_fallback_call()
            circuit_breaker_failures_total.labels(component="summarize", error_type="timeout").inc()
            logger.warning(
                "[Summarize] Progress-aware timeout (%s) — degrading to deterministic fallback",
                timeout_exc,
            )
            await self._emit_compaction_status(context, "fallback", reason="timeout")
            return self._apply_deterministic_fallback(context, original_tokens, last_msg_db_id)
        except Exception as exc:
            from myrm_agent_harness.observability.auth_detector import (
                detect_auth_failure,
                get_auth_error_hint,
            )

            prev = _get_failures()

            error_type_classified = _classify_error_type(exc)

            if detect_auth_failure(exc):
                _set_failures(MAX_CONSECUTIVE_SUMMARIZE_FAILURES, "auth")
                _record_fallback_call()
                auth_hint = get_auth_error_hint(exc)
                logger.error(
                    "[Summarize] Auth failure — circuit breaker opened (30min cooldown) | %s: %s | Hint: %s",
                    type(exc).__name__,
                    exc,
                    auth_hint,
                )
                circuit_breaker_failures_total.labels(component="summarize", error_type="auth").inc()
                circuit_breaker_state.labels(component="summarize").set(2)  # OPEN
                return self._apply_deterministic_fallback(context, original_tokens, last_msg_db_id)

            _set_failures(prev + 1, error_type_classified)
            _record_fallback_call()

            metrics_error_type = (
                error_type_classified
                if error_type_classified != "transient"
                else ("timeout" if "timeout" in str(exc).lower() else "other")
            )
            circuit_breaker_failures_total.labels(component="summarize", error_type=metrics_error_type).inc()

            if prev + 1 >= MAX_CONSECUTIVE_SUMMARIZE_FAILURES:
                circuit_breaker_state.labels(component="summarize").set(2)  # OPEN

            logger.warning(
                "[Summarize] LLM failed (%d/%d) [type: %s, cooldown: %ds] | %s: %s — using deterministic fallback",
                prev + 1,
                MAX_CONSECUTIVE_SUMMARIZE_FAILURES,
                error_type_classified,
                _cooldown_seconds(),
                type(exc).__name__,
                exc,
            )
            await self._emit_compaction_status(context, "fallback", reason=error_type_classified)
            return self._apply_deterministic_fallback(context, original_tokens, last_msg_db_id)

        _set_failures(0)
        global _skip_next_api_token_check
        _reset_fallback_calls()
        _skip_next_api_token_check = True
        circuit_breaker_state.labels(component="summarize").set(0)  # CLOSED (recovered)

        new_tokens = estimate_messages_tokens(context.messages)
        saved = original_tokens - new_tokens
        context.tokens_saved += saved

        await self._emit_compaction_status(
            context,
            "completed",
            tokens_saved=saved,
            dropped_manifest=summary.dropped_manifest,
        )

        context.structured_summary = summary
        if isinstance(last_msg_db_id, str) and last_msg_db_id:
            context.last_summarized_message_id = last_msg_db_id

        from ....infra.cache_break_detector import get_cache_break_detector

        detector = get_cache_break_detector()
        if detector is not None:
            detector.notify_compaction()

        logger.info(
            "[Summarize] done | goal: %s... | saved: %d tokens",
            summary.user_goal[:50],
            saved,
        )

        return context

    def _apply_structured_summary(
        self,
        context: ProcessorContext,
        summary: StructuredSummary,
        original_tokens: int,
        last_msg_db_id: object,
    ) -> ProcessorContext:
        """Apply an external/replacement structured summary directly without LLM call."""
        new_tokens = assemble_summarized_messages(context, summary, self.config)
        saved = max(0, original_tokens - new_tokens)
        context.tokens_saved += saved
        context.structured_summary = summary
        context.metadata["pre_compact_replacement_applied"] = True
        context.metadata.pop("compaction_debt_pending", None)
        if isinstance(last_msg_db_id, str) and last_msg_db_id:
            context.last_summarized_message_id = last_msg_db_id

        global _skip_next_api_token_check
        _skip_next_api_token_check = True

        logger.info(
            "[Summarize] replacement structured summary applied directly | goal: %.50s... | saved: %d tokens",
            summary.user_goal,
            saved,
        )
        return context

    def _apply_deterministic_fallback(
        self, context: ProcessorContext, original_tokens: int, last_msg_db_id: object
    ) -> ProcessorContext:
        """Deterministic fallback: build a minimal summary without LLM."""
        summary = _build_deterministic_summary(context.messages, context.metadata, context.chat_id)
        new_tokens = assemble_summarized_messages(context, summary, self.config)
        saved = original_tokens - new_tokens
        context.tokens_saved += saved

        context.structured_summary = summary
        context.metadata["summarize_fallback_used"] = True
        if isinstance(last_msg_db_id, str) and last_msg_db_id:
            context.last_summarized_message_id = last_msg_db_id

        global _skip_next_api_token_check
        _skip_next_api_token_check = True

        logger.info(
            "[Summarize] deterministic fallback applied | goal: %s... | saved: %d tokens",
            summary.user_goal[:50],
            saved,
        )
        return context
