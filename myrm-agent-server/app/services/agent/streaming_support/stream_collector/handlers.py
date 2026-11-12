"""[INPUT]
- app.services.agent.streaming_support.evicted_output::attach_evicted_to_step / find_step_for_evicted / parse_evicted_ref_payload / step_accepts_pending_evicted (POS: Stateless helpers for stream_collector. Evicted output arrives as its own event, before or after the tool step it belongs to, so the collector holds it until a step accepts it.)
- app.services.agent.streaming_support.stream_collector_helpers::collect_clarification_required / collect_cron_job_result / collect_file_mutation_failures / collect_kanban_task_created / collect_plan_confirmation_status / is_memory_citation_tool / iteration_limit_message / merge_sources_list / merge_tasks_step / string_keyed_dict / string_keyed_dicts (POS: Stateless parsing helpers for stream_collector; they hold no collector state, so each can be read and tested alone.)
- app.services.skills.mutation_batch_stream::link_batch_to_step (POS: Dependency-free contract module shared by the hook (producer) and stream_collector (consumer).)
- app.services.agent.streaming_support.stream_collector.base::StreamCollectorBase (POS: handlers 与 state 两个 mixin 共用的实例属性类型，集中一处避免重复注解。)
- app.services.agent.streaming_support.stream_collector.constants::_FAILOVER_REASON_TO_STEP_KEY / _PERSISTED_STATUS_STEP_KEYS (POS: handlers / state / core 共用的限制与事件映射。)
- app.services.agent.streaming_support.stream_collector.state::_sync_run_digest (POS: StreamContentCollector 的状态更新 mixin；只改内存状态，不读事件流。)

[OUTPUT]
- StreamEventHandlersMixin

[POS]
StreamContentCollector 的事件处理 mixin；每个 _on_<type> 负责一类事件。
"""

from __future__ import annotations

from app.services.agent.streaming_support.evicted_output import (
    attach_evicted_to_step,
    find_step_for_evicted,
    parse_evicted_ref_payload,
    step_accepts_pending_evicted,
)
from app.services.agent.streaming_support.stream_collector_helpers import (
    collect_clarification_required,
    collect_cron_job_result,
    collect_file_mutation_failures,
    collect_kanban_task_created,
    collect_plan_confirmation_status,
    is_memory_citation_tool,
    iteration_limit_message,
    merge_sources_list,
    merge_tasks_step,
    string_keyed_dict,
    string_keyed_dicts,
)
from app.services.skills.mutation_batch_stream import link_batch_to_step

from .base import StreamCollectorBase
from .constants import _FAILOVER_REASON_TO_STEP_KEY, _PERSISTED_STATUS_STEP_KEYS
from .state import _sync_run_digest


class StreamEventHandlersMixin(StreamCollectorBase):
    """按事件类型收集内容、步骤、usage 与中断信息。"""

    def _on_iteration_limit_reached(self, event: dict[str, object], data: object) -> None:
        detail = string_keyed_dict(data) if isinstance(data, dict) else None
        payload: dict[str, object] = {
            "code": "iteration_limit_reached",
            "category": "limit",
            "message": iteration_limit_message(detail),
        }
        if detail is not None:
            payload["detail"] = detail
        self._set_stop_reason(payload)

    def _on_engine_limit_reached(self, event: dict[str, object], data: object) -> None:
        detail = string_keyed_dict(data) if isinstance(data, dict) else None
        message = "Engine limit reached"
        if detail is not None:
            raw_message = detail.get("message")
            if isinstance(raw_message, str) and raw_message.strip():
                message = raw_message.strip()
        payload: dict[str, object] = {
            "code": "engine_limit_reached",
            "category": "limit",
            "message": message,
        }
        if detail is not None:
            payload["detail"] = detail
        self._set_stop_reason(payload)

    def _on_agent_cancelled(self, event: dict[str, object], data: object) -> None:
        detail = string_keyed_dict(data) if isinstance(data, dict) else None
        reason = detail.get("reason") if detail else None
        message = "Cancelled by user" if reason == "user_cancelled" else "Run cancelled"
        payload: dict[str, object] = {
            "code": "agent_cancelled",
            "category": "cancelled",
            "message": message,
        }
        if detail is not None:
            payload["detail"] = detail
        self._set_stop_reason(payload)
        self.mark_stream_completion_cancelled()

    def _on_error(self, event: dict[str, object], data: object) -> None:
        raw_error = event.get("error")
        error_message = ""
        if isinstance(raw_error, str) and raw_error.strip():
            error_message = raw_error.strip()
        elif isinstance(data, str) and data.strip():
            error_message = data.strip()
        if error_message:
            detail: dict[str, object] = {}
            error_type = event.get("error_type")
            if isinstance(error_type, str) and error_type.strip():
                detail["error_type"] = error_type.strip()
            payload: dict[str, object] = {
                "code": "error",
                "category": "error",
                "message": error_message,
            }
            if detail:
                payload["detail"] = detail
            self._set_stop_reason(payload)

    def _on_reasoning(self, event: dict[str, object], data: object) -> None:
        if not data:
            return
        self._append_reasoning(str(data))

    def _on_sources(self, event: dict[str, object], data: object) -> None:
        if not isinstance(data, list):
            return
        incoming = string_keyed_dicts(data)
        if incoming:
            self._sources = merge_sources_list(self._sources, incoming)

    def _on_file_mutation_failed(self, event: dict[str, object], data: object) -> None:
        collect_file_mutation_failures(self._file_mutation_failures, data)

    def _on_council_phase(self, event: dict[str, object], data: object) -> None:
        if not isinstance(data, dict):
            return
        phase_entry = string_keyed_dict(data)
        if phase_entry is not None:
            self._council_phases.append(phase_entry)

    def _on_tasks_steps(self, event: dict[str, object], data: object) -> None:
        tool_details = event.get("tool_result_details")
        if isinstance(tool_details, dict):
            self._tool_result_details = tool_details
        step = merge_tasks_step(self._progress_steps, event, data)
        batch_id = step.get("skill_mutation_batch_id")
        if isinstance(batch_id, str) and batch_id.strip():
            event["skill_mutation_batch_id"] = batch_id.strip()
        if self._pending_evicted:
            remaining: list[dict[str, object]] = []
            for pending in self._pending_evicted:
                if step_accepts_pending_evicted(step, pending):
                    attach_evicted_to_step(step, pending)
                else:
                    remaining.append(pending)
            self._pending_evicted = remaining
        _sync_run_digest(self)

    def _on_token_usage(self, event: dict[str, object], data: object) -> None:
        if not isinstance(data, dict):
            return
        self._usage = string_keyed_dict(data.get("usage"))

    def _on_message_end(self, event: dict[str, object], data: object) -> None:
        self._flush_pending_evicted_ref()
        turn_loaded = event.get("turn_loaded_skills")
        if isinstance(turn_loaded, list) and turn_loaded:
            self._turn_loaded_skills = [item for item in turn_loaded if isinstance(item, dict)]
        staged = event.get("staged_artifacts")
        if isinstance(staged, list):
            self._staged_artifacts.extend(string_keyed_dicts(staged))
        deliverable_tier = string_keyed_dict(event.get("deliverable_tier"))
        if deliverable_tier is not None:
            self._deliverable_tier = deliverable_tier
        usage = string_keyed_dict(event.get("usage"))
        if usage is not None:
            self._usage = usage
        token_economics = string_keyed_dict(event.get("token_economics"))
        if token_economics is not None:
            self._token_economics = token_economics
        context_budget = string_keyed_dict(event.get("context_budget"))
        if context_budget is not None:
            self._context_budget = context_budget
        cost = event.get("cost_usd")
        if isinstance(cost, (int, float)):
            self._cost_usd = float(cost)
        cost_status = event.get("cost_status")
        if isinstance(cost_status, str):
            self._cost_status = cost_status
        completion_status = event.get("completion_status")
        if isinstance(completion_status, str):
            self._completion_status = completion_status
        stream_ttft_ms = event.get("stream_ttft_ms")
        if isinstance(stream_ttft_ms, (int, float)) and stream_ttft_ms >= 0:
            self._stream_ttft_ms = int(stream_ttft_ms)
        model = event.get("model")
        if isinstance(model, str):
            self._model_name = model
        usage_alert = string_keyed_dict(event.get("usage_alert"))
        if usage_alert is not None:
            self._usage_alert = usage_alert
        cited = event.get("cited_memory_ids")
        if isinstance(cited, list):
            for mid in cited:
                if isinstance(mid, str) and mid not in self._cited_memory_ids:
                    self._cited_memory_ids.append(mid)
        refs = event.get("cited_memory_refs")
        if isinstance(refs, list):
            self._extend_cited_memory_refs(refs)

    def _on_tool_stdout_chunk(self, event: dict[str, object], data: object) -> None:
        if not isinstance(data, str):
            return
        tool_name = event.get("tool_name")
        if isinstance(tool_name, str):
            for step in reversed(self._progress_steps):
                if step.get("tool_name") == tool_name:
                    prev = step.get("stdout")
                    step["stdout"] = f"{prev}{data}" if isinstance(prev, str) else data
                    break

    def _on_tool_evicted_ref(self, event: dict[str, object], data: object) -> None:
        evicted_payload = parse_evicted_ref_payload(data, event)
        if evicted_payload is not None:
            matched = find_step_for_evicted(self._progress_steps, evicted_payload)
            if matched is not None:
                attach_evicted_to_step(matched, evicted_payload)
            else:
                self._pending_evicted.append(evicted_payload)

    def _on_tool_end(self, event: dict[str, object], data: object) -> None:
        cited = event.get("cited_memory_ids")
        is_memory_recall = is_memory_citation_tool(event.get("tool_name"))
        if is_memory_recall and isinstance(cited, list):
            for mid in cited:
                if isinstance(mid, str) and mid not in self._cited_memory_ids:
                    self._cited_memory_ids.append(mid)
        refs = event.get("cited_memory_refs")
        if is_memory_recall and isinstance(refs, list):
            self._extend_cited_memory_refs(refs)
        trace = event.get("memory_retrieval_trace")
        if is_memory_recall and isinstance(trace, dict):
            self._append_memory_retrieval_trace(trace)
        collect_kanban_task_created(self._kanban_tasks_created, event)
        cron_result = collect_cron_job_result(event)
        if cron_result is not None:
            self._cron_job_result = cron_result
        link_batch_to_step(self._progress_steps, event)

    def _on_routing_decision(self, event: dict[str, object], data: object) -> None:
        if not isinstance(data, dict):
            return
        tier = data.get("tier")
        if isinstance(tier, str):
            self._routing_tier = tier
        reason = data.get("reason")
        if isinstance(reason, str):
            self._routing_reason = reason

    def _on_privacy_level(self, event: dict[str, object], data: object) -> None:
        if not isinstance(data, dict):
            return
        level = data.get("current_turn_level")
        if isinstance(level, str):
            self._privacy_level = level

    def _on_privacy_route(self, event: dict[str, object], data: object) -> None:
        if not isinstance(data, dict):
            return
        route = data.get("route")
        if isinstance(route, str):
            self._privacy_route = route

    def _on_session_recording(self, event: dict[str, object], data: object) -> None:
        if not isinstance(data, dict):
            return
        self._session_recording = string_keyed_dict(data)

    def _on_clarification_required(self, event: dict[str, object], data: object) -> None:
        clarification = collect_clarification_required(event)
        if clarification is not None:
            self._clarification = clarification

    def _on_status(self, event: dict[str, object], data: object) -> None:
        step_key = event.get("step_key")
        if isinstance(data, dict):
            phase_payload = string_keyed_dict(data)
            if phase_payload is not None:
                plan_update = collect_plan_confirmation_status(phase_payload)
                if plan_update is not None:
                    if self._plan_confirmation is None:
                        self._plan_confirmation = plan_update
                    else:
                        self._plan_confirmation = {
                            **self._plan_confirmation,
                            **plan_update,
                        }
        if step_key == "cache_break" and isinstance(data, dict):
            self._cache_break = data
        if event.get("restart") is True:
            # Recovery STATUS steps (transient_retry, context_compaction, ...)
            # precede a from-scratch re-run; drop any streamed draft.
            self._discard_draft()
        if step_key == "model_failover":
            error_kind = event.get("error_kind")
            display_key = f"model_failover_{error_kind}" if isinstance(error_kind, str) and error_kind else "model_failover"
            fallback_model = event.get("fallback_model")
            item_text = str(fallback_model) if fallback_model else ""
            self._append_failover_step(display_key, item_text)
        if isinstance(step_key, str) and step_key in _PERSISTED_STATUS_STEP_KEYS:
            step = {
                "step_key": step_key,
                "tool_name": event.get("tool_name"),
                "items": event.get("items"),
                "status": event.get("status"),
            }
            if isinstance(data, dict):
                archive_restore_block = string_keyed_dict(data.get("archive_restore_block"))
                if archive_restore_block is not None:
                    step["archive_restore_block"] = archive_restore_block
                archive_restore_result = string_keyed_dict(data.get("archive_restore_result"))
                if archive_restore_result is not None:
                    step["archive_restore_result"] = archive_restore_result
            self._progress_steps.append(step)

    def _on_model_failover(self, event: dict[str, object], data: object) -> None:
        if not isinstance(data, dict):
            return
        reason = data.get("reason")
        from_model = data.get("fromModel")
        to_model = data.get("toModel")
        reason_key = str(reason) if reason is not None else ""
        display_key = _FAILOVER_REASON_TO_STEP_KEY.get(reason_key, "model_failover")
        label_parts = [str(v) for v in (from_model, to_model) if v]
        self._append_failover_step(display_key, " → ".join(label_parts))
