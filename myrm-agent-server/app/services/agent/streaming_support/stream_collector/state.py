"""[INPUT]
- myrm_agent_harness.agent.streaming.citation_audit::audit_citation_markers / resolve_source_count_for_audit (POS: Shared streaming helper; used by server persistence.)
- myrm_agent_harness.toolkits.code_execution.executors.models::scrub_sensitive_info (POS: Data models for code execution.)
- myrm_agent_harness.utils.text_sanitizer::sanitize_llm_output (POS: LLM streaming output sanitizer. Four-layer filtering ensures clean, garble-free text for user display; layer 4 alone is exposed for user-authored text, where tags are content rather than protocol leakage.)
- app.core.agent.stop_reason::merge_stop_reason (POS: The chat stream collector (services), the cron runner (core) and the Runs Hub (api) all store and read the same ``stopReason`` shape; this is the one definition they share.)
- app.services.agent.streaming_support.evicted_output::BASH_EXECUTE_TOOL / attach_evicted_to_step / find_step_for_evicted (POS: Stateless helpers for stream_collector. Evicted output arrives as its own event, before or after the tool step it belongs to, so the collector holds it until a step accepts it.)
- app.services.agent.streaming_support.stream_collector.base::StreamCollectorBase (POS: handlers 与 state 两个 mixin 共用的实例属性类型，集中一处避免重复注解。)
- app.services.agent.streaming_support.stream_collector.constants::_MAX_REASONING_CHARS (POS: handlers / state / core 共用的限制与事件映射。)

[OUTPUT]
- StreamStateMixin

[POS]
StreamContentCollector 的状态更新 mixin；只改内存状态，不读事件流。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from myrm_agent_harness.agent.streaming.citation_audit import (
    audit_citation_markers,
    resolve_source_count_for_audit,
)
from myrm_agent_harness.toolkits.code_execution.executors.models import (
    scrub_sensitive_info,
)
from myrm_agent_harness.utils.text_sanitizer import sanitize_llm_output

from app.core.agent.stop_reason import merge_stop_reason
from app.services.agent.streaming_support.evicted_output import (
    BASH_EXECUTE_TOOL,
    attach_evicted_to_step,
    find_step_for_evicted,
)

from .base import StreamCollectorBase
from .constants import _MAX_REASONING_CHARS

if TYPE_CHECKING:
    pass


class StreamStateMixin(StreamCollectorBase):
    """把收集到的片段整理成快照、草稿与步骤。"""

    @property
    def content(self) -> str:
        return self._answer.text

    @property
    def reasoning(self) -> str | None:
        return "".join(self._reasoning_parts) if self._reasoning_parts else None

    @property
    def has_content(self) -> bool:
        return bool(self._answer) or bool(self._reasoning_parts)

    @property
    def completion_status(self) -> str | None:
        """How the stream said the turn ended (``complete``, ``cancelled``, ``error``); ``None`` until it said so."""
        return self._completion_status

    @property
    def has_persistable_turn(self) -> bool:
        """True when finalize should persist an assistant message row."""
        return self.has_content or self.extra_data is not None

    @property
    def has_active_generation(self) -> bool:
        """True when authentic model output (text, reasoning, or tool step) was collected."""
        return self.has_content or bool(self._progress_steps) or bool(self._clarification)

    @property
    def sibling_group_id(self) -> str | None:
        return self._sibling_group_id

    def _discard_draft(self) -> None:
        """Drop partial content streamed before a recovery that restarts the turn.

        Every recovery that makes the LLM regenerate the in-flight answer segment
        (model failover, transient retry, context compaction, ...)
        emits its STATUS/SSE event synchronously *before* the restreamed chunks,
        so the text of that segment is a draft that will be fully regenerated.
        Dropping it (idempotent: a second event finds nothing left to drop) keeps
        both the persisted history and the live stream free of stale partial
        content spliced with the complete answer. Text before the last tool step
        belongs to a checkpointed segment and stays (see ``AnswerDraft``).
        """
        self._answer.restart()
        self._reasoning_parts.clear()
        self._reasoning_char_count = 0
        self._reasoning_truncated = False
        self._tool_result_details = None

    def _append_failover_step(self, step_key: str, item_text: str) -> None:
        """Append a failover progress step, deduplicating STATUS + SSE notify channels.

        The harness emits both a STATUS ``model_failover`` / ``safety_fallback_active``
        event and a ``model_failover`` SSE event for the same transition; persist
        only one step, keeping the more complete (from → to) label when present.
        Prefix matching (not exact step_key) keeps the two channels in sync even
        when the SSE ``reason`` has no direct STATUS ``error_kind`` mapping
        (e.g. PROVIDER_POLICY_BLOCKED → ``model_failover`` vs
        ``model_failover_model_not_found``), and folds the safety-fallback
        channel (``safety_fallback_active``) into the same dedupe.
        """
        self._discard_draft()
        for existing in self._progress_steps:
            key = str(existing.get("step_key", ""))
            if not (key.startswith("model_failover") or key == "safety_fallback_active"):
                continue
            if item_text:
                existing_items = existing.get("items")
                existing_label = (
                    str(existing_items[0].get("text", ""))
                    if isinstance(existing_items, list) and existing_items and isinstance(existing_items[0], dict)
                    else ""
                )
                # Keep the more complete "from → to" label when already present:
                # the SSE notify channel is fed synchronously in _handle_failover,
                # so it usually arrives before the STATUS event carrying only the
                # fallback model name.
                if "→" not in existing_label:
                    existing["items"] = [{"text": item_text}]
            return
        self._progress_steps.append(
            {
                "step_key": step_key,
                "items": [{"text": item_text}] if item_text else [],
                "status": "success",
            }
        )

    def _flush_pending_evicted_ref(self) -> None:
        if not self._pending_evicted:
            return
        for payload in self._pending_evicted:
            matched = find_step_for_evicted(self._progress_steps, payload)
            if matched is not None:
                attach_evicted_to_step(matched, payload)
                continue
            tool_hint = payload.get("tool_name")
            fallback: dict[str, object] = {
                "tool_name": (tool_hint if isinstance(tool_hint, str) else BASH_EXECUTE_TOOL),
            }
            tool_call_id = payload.get("tool_call_id")
            if isinstance(tool_call_id, str) and tool_call_id.strip():
                fallback["tool_call_id"] = tool_call_id.strip()
            attach_evicted_to_step(fallback, payload)
            self._progress_steps.append(fallback)
        self._pending_evicted = []

    @property
    def extra_data(self) -> dict[str, object] | None:
        """Build extra_data dict for DB storage. Returns None if empty."""
        result: dict[str, object] = {}
        if self._sources:
            result["sources"] = self._sources
            content = self.content
            if content:
                source_count = resolve_source_count_for_audit(self._sources)
                audit = audit_citation_markers(content, source_count)
                if audit.total_markers > 0:
                    result["citationAudit"] = {
                        "totalMarkers": audit.total_markers,
                        "valid": audit.valid,
                        "unresolved": audit.unresolved,
                    }
        if self._stop_reason:
            result["stopReason"] = self._stop_reason
        if self._progress_steps:
            result["progressSteps"] = self._progress_steps
        if self._usage:
            result["usage"] = self._usage
        if self._context_budget:
            result["contextBudget"] = self._context_budget
        if self._cost_usd is not None:
            result["costUsd"] = self._cost_usd
        if self._cost_status:
            result["costStatus"] = self._cost_status
        if self._completion_status:
            result["completionStatus"] = self._completion_status
        if self._stream_ttft_ms is not None:
            result["streamTtftMs"] = self._stream_ttft_ms

        if self._usage_alert:
            result["usageAlert"] = self._usage_alert

        if self._model_name:
            result["modelName"] = self._model_name
        if self._token_economics:
            result["tokenEconomics"] = self._token_economics
        if self._routing_tier:
            result["routingTier"] = self._routing_tier
        if self._routing_reason:
            result["routingReason"] = self._routing_reason
        if self._privacy_level:
            result["privacyLevel"] = self._privacy_level
        if self._privacy_route:
            result["privacyRoute"] = self._privacy_route
        if self._cache_break:
            result["cacheBreak"] = self._cache_break
        if self._cited_memory_ids:
            result["citedMemoryIds"] = self._cited_memory_ids
        if self._cited_memory_refs:
            result["citedMemoryRefs"] = self._cited_memory_refs
        if self._turn_loaded_skills:
            result["turnLoadedSkills"] = self._turn_loaded_skills
        if self._memory_retrieval_traces:
            result["memoryRetrievalTraces"] = self._memory_retrieval_traces
        if self._session_recording:
            result["sessionRecording"] = self._session_recording
        if self._clarification:
            result["clarification"] = self._clarification
        if self._plan_confirmation:
            result["planConfirmation"] = self._plan_confirmation
        if self._staged_artifacts:
            result["stagedArtifacts"] = self._staged_artifacts
        if self._deliverable_tier is not None:
            result["deliverableTier"] = self._deliverable_tier
        if self._kanban_tasks_created:
            result["kanban_tasks_created"] = list(self._kanban_tasks_created)
        if self._cron_job_result is not None:
            result["cron_job_result"] = self._cron_job_result
        if self._file_mutation_failures:
            result["fileMutationFailures"] = list(self._file_mutation_failures)
        if self._council_phases:
            result["councilPhases"] = list(self._council_phases)
        if self._tool_result_details:
            result["tool_result_details"] = self._tool_result_details
        if self.reasoning:
            result["reasoning"] = self.reasoning
            if self._reasoning_truncated:
                result["reasoningTruncated"] = True
                result["reasoningCharLimit"] = _MAX_REASONING_CHARS
        return result or None

    def _set_stop_reason(self, payload: dict[str, object]) -> None:
        self._stop_reason = merge_stop_reason(self._stop_reason, payload)

    def _extend_cited_memory_refs(self, refs: list[object]) -> None:
        seen = {str(ref.get("id")) for ref in self._cited_memory_refs if isinstance(ref.get("id"), str)}
        for ref in refs:
            if not isinstance(ref, dict):
                continue
            ref_id = ref.get("id")
            if not isinstance(ref_id, str) or not ref_id or ref_id in seen:
                continue
            normalized = {str(key): value for key, value in ref.items() if isinstance(key, str)}
            self._cited_memory_refs.append(normalized)
            seen.add(ref_id)

    def _append_memory_retrieval_trace(self, trace: dict[object, object]) -> None:
        trace_id = trace.get("id")
        if not isinstance(trace_id, str) or not trace_id:
            return
        if any(existing.get("id") == trace_id for existing in self._memory_retrieval_traces):
            return
        normalized = {str(key): value for key, value in trace.items() if isinstance(key, str)}
        self._memory_retrieval_traces.append(normalized)

    def _append_reasoning(self, chunk: str) -> None:
        if not chunk:
            return
        remaining = _MAX_REASONING_CHARS - self._reasoning_char_count
        if remaining <= 0:
            self._reasoning_truncated = True
            return
        raw_chunk = chunk
        if len(raw_chunk) > remaining:
            raw_chunk = raw_chunk[:remaining]
            self._reasoning_truncated = True

        safe_chunk = scrub_sensitive_info(sanitize_llm_output(raw_chunk))
        if not safe_chunk:
            return

        if len(safe_chunk) <= remaining:
            self._reasoning_parts.append(safe_chunk)
            self._reasoning_char_count += len(safe_chunk)
            return

        self._reasoning_parts.append(safe_chunk[:remaining])
        self._reasoning_char_count += remaining
        self._reasoning_truncated = True


def _sync_run_digest(collector: StreamCollectorBase) -> None:
    chat_id = collector._chat_id
    if not chat_id:
        return
    from app.services.copilot.run_digest_store import RunDigestStore

    RunDigestStore.update_from_progress(chat_id, collector._progress_steps)

