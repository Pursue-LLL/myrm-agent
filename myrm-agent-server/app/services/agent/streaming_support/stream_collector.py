"""SSE stream content collector for persisting assistant messages with metadata.

[INPUT]
JSON SSE chunks and parsed Agent stream events (POS: Agent runtime event stream)
- stream_collector_helpers (POS: stateless SSE event parsing helpers)
- myrm_agent_harness.toolkits.code_execution.executors.models::scrub_sensitive_info
  (POS: Harness-level sensitive token/path scrubbing)
- myrm_agent_harness.utils.text_sanitizer::sanitize_llm_output
  (POS: LLM raw text sanitizer for control/sentinel cleanup)

[OUTPUT]
StreamContentCollector: collects assistant content and message extra_data, including memory citation refs,
retrieval traces, end-to-end stream TTFT (`streamTtftMs`), kanban_tasks_created, cron_job_result,
HITL clarification (`clarification`), deep-research plan confirmation (`planConfirmation`),
file mutation failures (`fileMutationFailures`), council phase progress (`councilPhases`),
and reasoning safety metadata (`reasoningTruncated` / `reasoningCharLimit`).

[POS]
Agent API persistence helper. Converts transient SSE events into durable Message.extra_data metadata.
"""

from __future__ import annotations

import asyncio
import json
import logging

from myrm_agent_harness.toolkits.code_execution.executors.models import (
    scrub_sensitive_info,
)
from myrm_agent_harness.utils.text_sanitizer import sanitize_llm_output

from app.services.agent.streaming_support.stream_collector_helpers import (
    collect_clarification_required,
    collect_cron_job_result,
    collect_file_mutation_failures,
    collect_kanban_task_created,
    collect_plan_confirmation_status,
    deep_merge_ui_data,
    is_memory_citation_tool,
    string_keyed_dict,
    string_keyed_dicts,
)

_SSE_DATA_PREFIX = "data: "
_MAX_REASONING_CHARS = 24_000
_PERSISTED_STATUS_STEP_KEYS = frozenset(
    {"archive_restore_blocked", "archive_restore_result"}
)
logger = logging.getLogger(__name__)
_STOP_REASON_CATEGORIES = frozenset({"limit", "cancelled", "error", "other"})


def _stop_reason_priority(code: str) -> int:
    if code in {"iteration_limit_reached", "engine_limit_reached"}:
        return 40
    if code == "agent_cancelled":
        return 30
    if code == "error":
        return 20
    return 10


def _normalize_stop_reason(raw: dict[str, object] | None) -> dict[str, object] | None:
    if raw is None:
        return None
    code_obj = raw.get("code")
    if not isinstance(code_obj, str) or not code_obj.strip():
        return None
    code = code_obj.strip()
    category_obj = raw.get("category")
    if isinstance(category_obj, str) and category_obj in _STOP_REASON_CATEGORIES:
        category = category_obj
    else:
        category = "other"
    message_obj = raw.get("message")
    if isinstance(message_obj, str) and message_obj.strip():
        message = message_obj.strip()
    else:
        message = code.replace("_", " ")
    normalized: dict[str, object] = {
        "code": code,
        "category": category,
        "message": message,
    }
    detail = string_keyed_dict(raw.get("detail"))
    if detail:
        normalized["detail"] = detail
    return normalized


def _iteration_limit_message(detail: dict[str, object] | None) -> str:
    if detail is None:
        return "Iteration limit reached"
    limit = detail.get("limit")
    nodes = detail.get("nodes_completed")
    if limit is not None and nodes is not None:
        return f"Iteration limit reached ({limit} iterations / {nodes} nodes)"
    if limit is not None:
        return f"Iteration limit reached ({limit} iterations)"
    return "Iteration limit reached"


def _ensure_evicted_stdout_preview(step: dict[str, object]) -> None:
    stdout = step.get("stdout")
    if isinstance(stdout, str) and stdout.strip():
        return
    step["stdout"] = (
        "[LARGE OUTPUT TRUNCATED]\n\n(Full output evicted to workspace file)"
    )


_BASH_EXECUTE_TOOL = "bash_code_execute_tool"
_MAX_EVICTED_PREVIEW_CHARS = 8_000


def _cap_evicted_preview(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    if len(text) > _MAX_EVICTED_PREVIEW_CHARS:
        return text[:_MAX_EVICTED_PREVIEW_CHARS]
    return text


def _parse_evicted_ref_payload(
    data: object,
    event: dict[str, object],
) -> dict[str, object] | None:
    payload: dict[str, object] = {}
    if isinstance(data, str) and data.strip():
        payload["evicted_ref"] = data.strip()
    elif isinstance(data, dict):
        raw_ref = data.get("evicted_ref")
        if isinstance(raw_ref, str) and raw_ref.strip():
            payload["evicted_ref"] = raw_ref.strip()
        tool_name = data.get("tool_name")
        if isinstance(tool_name, str) and tool_name.strip():
            payload["tool_name"] = tool_name.strip()
        tool_call_id = data.get("tool_call_id")
        if isinstance(tool_call_id, str) and tool_call_id.strip():
            payload["tool_call_id"] = tool_call_id.strip()
        preview = _cap_evicted_preview(data.get("preview_stdout"))
        if preview:
            payload["preview_stdout"] = preview
        stored_chars = data.get("stored_chars")
        if isinstance(stored_chars, int) and stored_chars > 0:
            payload["stored_chars"] = stored_chars
        total_lines = data.get("total_lines")
        if isinstance(total_lines, int) and total_lines > 0:
            payload["total_lines"] = total_lines
        storage_truncated = data.get("storage_truncated")
        if storage_truncated is True:
            payload["storage_truncated"] = True
    event_tool = event.get("tool_name")
    if (
        isinstance(event_tool, str)
        and event_tool.strip()
        and "tool_name" not in payload
    ):
        payload["tool_name"] = event_tool.strip()
    ref = payload.get("evicted_ref")
    return payload if isinstance(ref, str) and ref else None


def _attach_evicted_to_step(
    step: dict[str, object], payload: dict[str, object]
) -> None:
    ref = payload.get("evicted_ref")
    if not isinstance(ref, str) or not ref:
        return
    step["evicted_file_ref"] = ref
    step["status"] = "success"
    preview = payload.get("preview_stdout")
    if isinstance(preview, str) and preview.strip():
        step["stdout"] = preview
    else:
        _ensure_evicted_stdout_preview(step)
    tool_call_id = payload.get("tool_call_id")
    if (
        isinstance(tool_call_id, str)
        and tool_call_id.strip()
        and not step.get("tool_call_id")
    ):
        step["tool_call_id"] = tool_call_id.strip()
    if not step.get("step_key"):
        step_tool = step.get("tool_name")
        if step_tool == _BASH_EXECUTE_TOOL:
            step["step_key"] = "bash_code_execute_tool_tool"
        elif isinstance(step_tool, str) and step_tool:
            step["step_key"] = step_tool
    stored_chars = payload.get("stored_chars")
    if isinstance(stored_chars, int) and stored_chars > 0:
        step["evicted_stored_chars"] = stored_chars
    total_lines = payload.get("total_lines")
    if isinstance(total_lines, int) and total_lines > 0:
        step["evicted_total_lines"] = total_lines
    if payload.get("storage_truncated") is True:
        step["evicted_storage_truncated"] = True


def _find_step_for_evicted(
    steps: list[dict[str, object]],
    payload: dict[str, object],
) -> dict[str, object] | None:
    tool_call_id = payload.get("tool_call_id")
    if isinstance(tool_call_id, str) and tool_call_id.strip():
        target_id = tool_call_id.strip()
        for step in reversed(steps):
            if step.get("tool_call_id") == target_id:
                return step
    tool_hint = payload.get("tool_name")
    if isinstance(tool_hint, str) and tool_hint.strip():
        for step in reversed(steps):
            if step.get("evicted_file_ref"):
                continue
            if step.get("tool_name") == tool_hint.strip():
                return step
    for step in reversed(steps):
        if step.get("evicted_file_ref"):
            continue
        if step.get("tool_name") == _BASH_EXECUTE_TOOL:
            return step
    return None


def _merge_tasks_step(
    progress_steps: list[dict[str, object]],
    event: dict[str, object],
    data: object,
) -> dict[str, object]:
    step_key = event.get("step_key")
    tool_name = event.get("tool_name")
    tool_call_id = event.get("tool_call_id")
    new_fields: dict[str, object] = {
        "step_key": step_key,
        "tool_name": tool_name,
        "items": data,
        "count": event.get("count"),
    }
    if isinstance(tool_call_id, str) and tool_call_id.strip():
        new_fields["tool_call_id"] = tool_call_id.strip()
    for key in ("reason", "status", "error", "error_hint", "error_category"):
        value = event.get(key)
        if value is not None:
            new_fields[key] = value

    if isinstance(tool_call_id, str) and tool_call_id.strip():
        target_id = tool_call_id.strip()
        for existing in progress_steps:
            if existing.get("tool_call_id") == target_id:
                for key, value in new_fields.items():
                    if value is not None:
                        existing[key] = value
                return existing

    if isinstance(step_key, str) and step_key.strip():
        for existing in reversed(progress_steps):
            if existing.get("step_key") != step_key:
                continue
            existing_id = existing.get("tool_call_id")
            if isinstance(tool_call_id, str) and tool_call_id.strip():
                if existing_id in (None, "", tool_call_id.strip()):
                    for key, value in new_fields.items():
                        if value is not None:
                            existing[key] = value
                    if not existing_id:
                        existing["tool_call_id"] = tool_call_id.strip()
                    return existing
            elif not existing_id:
                for key, value in new_fields.items():
                    if value is not None:
                        existing[key] = value
                return existing

    step = {key: value for key, value in new_fields.items() if value is not None}
    progress_steps.append(step)
    return step


def _step_accepts_pending_evicted(
    step: dict[str, object], payload: dict[str, object]
) -> bool:
    tool_call_id = payload.get("tool_call_id")
    if isinstance(tool_call_id, str) and tool_call_id.strip():
        return step.get("tool_call_id") == tool_call_id.strip()
    tool_hint = payload.get("tool_name")
    step_tool = step.get("tool_name")
    if isinstance(tool_hint, str) and tool_hint:
        return step_tool == tool_hint
    if step_tool == _BASH_EXECUTE_TOOL:
        return True
    step_key = step.get("step_key")
    return isinstance(step_key, str) and step_key.startswith("bash_code_execute_tool")


ACTIVE_COLLECTORS: dict[str, "StreamContentCollector"] = {}

_INTERRUPT_REPLAY_TYPES: frozenset[str] = frozenset(
    {
        "tool_approval_request",
        "approval_required",
        "clarification_required",
    }
)


class StreamContentCollector:
    """Collects content and metadata from SSE stream events.

    Supports two input formats:
    - SSE string chunks (general_agent): feed_sse("data: {...}\\n\\n")
    - Event dicts (via gateway): feed_event({...})
    """

    def __init__(
        self, sibling_group_id: str | None = None, chat_id: str | None = None
    ) -> None:
        self._content_parts: list[str] = []
        self._reasoning_parts: list[str] = []
        self._reasoning_char_count = 0
        self._reasoning_truncated = False
        self._sources: list[dict[str, object]] = []
        self._progress_steps: list[dict[str, object]] = []
        self._cited_memory_ids: list[str] = []
        self._cited_memory_refs: list[dict[str, object]] = []
        self._memory_retrieval_traces: list[dict[str, object]] = []
        self._usage: dict[str, object] | None = None
        self._context_budget: dict[str, object] | None = None
        self._cost_usd: float | None = None
        self._cost_status: str | None = None
        self._completion_status: str | None = None
        self._stream_ttft_ms: int | None = None
        self._stop_reason: dict[str, object] | None = None
        self._model_name: str | None = None
        self._routing_tier: str | None = None
        self._privacy_level: str | None = None
        self._privacy_route: str | None = None
        self._cache_break: dict[str, object] | None = None
        self._token_economics: dict[str, object] | None = None
        self._usage_alert: dict[str, object] | None = None
        self._session_recording: dict[str, object] | None = None
        self._clarification: dict[str, object] | None = None
        self._plan_confirmation: dict[str, object] | None = None
        self._ui_artifacts: list[dict[str, object]] = []
        self._pending_interrupt_events: list[dict[str, object]] = []
        self._cross_turn_data_updates: list[tuple[str, dict[str, object]]] = []
        self._kanban_tasks_created: list[dict[str, object]] = []
        self._cron_job_result: dict[str, object] | None = None
        self._file_mutation_failures: list[dict[str, object]] = []
        self._council_phases: list[dict[str, object]] = []
        self._pending_evicted: dict[str, object] | None = None
        self._sibling_group_id: str | None = sibling_group_id
        self._chat_id: str | None = chat_id
        self._subscribers: list[asyncio.Queue[dict[str, object]]] = []

        if self._chat_id:
            ACTIVE_COLLECTORS[self._chat_id] = self

    def has_pending_hitl_replay(self) -> bool:
        """True when attach subscribers may still need interrupt replay."""
        return bool(self._pending_interrupt_events)

    def cleanup(self) -> None:
        """Remove from active collectors registry."""
        if self._chat_id and ACTIVE_COLLECTORS.get(self._chat_id) is self:
            del ACTIVE_COLLECTORS[self._chat_id]

    def _schedule_cross_turn_ui_patch(
        self,
        surface_id: str,
        updates: dict[str, object],
    ) -> None:
        if self._chat_id is None:
            return
        import asyncio

        from app.services.chat.ui_artifact_patch import (
            patch_ui_artifact_data_by_surface_id,
        )

        chat_id = self._chat_id
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return

        async def _run_patch() -> None:
            try:
                patched = await patch_ui_artifact_data_by_surface_id(
                    chat_id, surface_id, updates
                )
                if not patched:
                    logger.warning(
                        "Immediate cross-turn ui patch skipped: surface_id=%s chat_id=%s",
                        surface_id,
                        chat_id,
                    )
            except Exception:
                logger.exception(
                    "Immediate cross-turn ui patch failed: surface_id=%s chat_id=%s",
                    surface_id,
                    chat_id,
                )

        loop.create_task(_run_patch())

    def unsubscribe(self, q: asyncio.Queue[dict[str, object]]) -> None:
        """Remove a subscriber queue from the active subscriber list."""
        if q in self._subscribers:
            self._subscribers.remove(q)

    @property
    def has_subscribers(self) -> bool:
        """Check if there are active subscribers."""
        return len(self._subscribers) > 0

    def get_snapshot(self) -> dict[str, object]:
        """Get the current snapshot without subscribing."""
        merged_steps_dict: dict[str, dict[str, object]] = {}
        ordered_steps: list[dict[str, object]] = []
        for step in self._progress_steps:
            step_id = step.get("id")
            if isinstance(step_id, str):
                if step_id not in merged_steps_dict:
                    merged_steps_dict[step_id] = step.copy()
                    ordered_steps.append(merged_steps_dict[step_id])
                else:
                    merged_steps_dict[step_id].update(step)
            else:
                ordered_steps.append(step)

        merged_sources_dict: dict[str, dict[str, object]] = {}
        ordered_sources: list[dict[str, object]] = []
        for source in self._sources:
            url = source.get("url")
            if isinstance(url, str):
                if url not in merged_sources_dict:
                    merged_sources_dict[url] = source.copy()
                    ordered_sources.append(merged_sources_dict[url])
                else:
                    merged_sources_dict[url].update(source)
            else:
                ordered_sources.append(source)

        return {
            "content": "".join(self._content_parts),
            "reasoning": "".join(self._reasoning_parts),
            "progress_steps": ordered_steps,
            "sources": ordered_sources,
            "ui_artifacts": self._ui_artifacts,
        }

    def subscribe(self) -> tuple[dict[str, object], asyncio.Queue[dict[str, object]]]:
        """Atomically get current snapshot and subscribe to future events."""
        q: asyncio.Queue[dict[str, object]] = asyncio.Queue()
        self._subscribers.append(q)
        for event in self._pending_interrupt_events:
            q.put_nowait(event)
        return self.get_snapshot(), q

    def feed_sse(self, chunk: str) -> None:
        """Parse an SSE-formatted string chunk and collect data."""
        if not chunk.startswith(_SSE_DATA_PREFIX):
            return
        try:
            event = string_keyed_dict(
                json.loads(chunk[len(_SSE_DATA_PREFIX) :].rstrip())
            )
            if event is None:
                return
            self._process_event(event)
            for q in self._subscribers:
                q.put_nowait(event)
        except (json.JSONDecodeError, TypeError):
            pass

    def feed_event(self, event: dict[str, object]) -> None:
        """Collect data from a pre-parsed event dict."""
        self._process_event(event)
        for q in self._subscribers:
            q.put_nowait(event)

    def _process_event(self, event: dict[str, object]) -> None:
        event_type = event.get("type")
        if isinstance(event_type, str) and event_type in _INTERRUPT_REPLAY_TYPES:
            self._pending_interrupt_events.append(event)
        data = event.get("data")

        if event_type == "message" and data:
            self._content_parts.append(str(data))
        elif event_type == "iteration_limit_reached":
            detail = string_keyed_dict(data) if isinstance(data, dict) else None
            payload: dict[str, object] = {
                "code": "iteration_limit_reached",
                "category": "limit",
                "message": _iteration_limit_message(detail),
            }
            if detail is not None:
                payload["detail"] = detail
            self._set_stop_reason(payload)
        elif event_type == "engine_limit_reached":
            detail = string_keyed_dict(data) if isinstance(data, dict) else None
            message = "Engine limit reached"
            if detail is not None:
                raw_message = detail.get("message")
                if isinstance(raw_message, str) and raw_message.strip():
                    message = raw_message.strip()
            payload_2: dict[str, object] = {
                "code": "engine_limit_reached",
                "category": "limit",
                "message": message,
            }
            if detail is not None:
                payload_2["detail"] = detail
            self._set_stop_reason(payload_2)
        elif event_type == "agent_cancelled":
            detail = string_keyed_dict(data) if isinstance(data, dict) else None
            reason = detail.get("reason") if detail else None
            message = (
                "Cancelled by user" if reason == "user_cancelled" else "Run cancelled"
            )
            payload_3: dict[str, object] = {
                "code": "agent_cancelled",
                "category": "cancelled",
                "message": message,
            }
            if detail is not None:
                payload_3["detail"] = detail
            self._set_stop_reason(payload_3)
        elif event_type == "error":
            raw_error = event.get("error")
            error_message = ""
            if isinstance(raw_error, str) and raw_error.strip():
                error_message = raw_error.strip()
            elif isinstance(data, str) and data.strip():
                error_message = data.strip()
            if error_message:
                detail_2: dict[str, object] = {}
                error_type = event.get("error_type")
                if isinstance(error_type, str) and error_type.strip():
                    detail_2["error_type"] = error_type.strip()
                payload_4: dict[str, object] = {
                    "code": "error",
                    "category": "error",
                    "message": error_message,
                }
                if detail_2:
                    payload_4["detail"] = detail_2
                self._set_stop_reason(payload_4)
        elif event_type == "reasoning" and data:
            self._append_reasoning(str(data))
        elif event_type == "sources" and isinstance(data, list):
            self._sources.extend(string_keyed_dicts(data))
        elif event_type == "file_mutation_failed":
            collect_file_mutation_failures(self._file_mutation_failures, data)
        elif event_type == "council_phase" and isinstance(data, dict):
            phase_entry = string_keyed_dict(data)
            if phase_entry is not None:
                self._council_phases.append(phase_entry)
        elif event_type == "tasks_steps":
            step = _merge_tasks_step(self._progress_steps, event, data)
            if self._pending_evicted and _step_accepts_pending_evicted(
                step, self._pending_evicted
            ):
                _attach_evicted_to_step(step, self._pending_evicted)
                self._pending_evicted = None
        elif event_type == "token_usage" and isinstance(data, dict):
            self._usage = string_keyed_dict(data.get("usage"))

        elif event_type == "message_end":
            self._flush_pending_evicted_ref()
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
        elif event_type == "tool_stdout_chunk" and isinstance(data, str):
            tool_name = event.get("tool_name")
            if isinstance(tool_name, str):
                for step in reversed(self._progress_steps):
                    if step.get("tool_name") == tool_name:
                        prev = step.get("stdout")
                        step["stdout"] = (
                            f"{prev}{data}" if isinstance(prev, str) else data
                        )
                        break
        elif event_type == "tool_evicted_ref":
            payload = _parse_evicted_ref_payload(data, event)
            if payload is not None:
                matched = _find_step_for_evicted(self._progress_steps, payload)
                if matched is not None:
                    _attach_evicted_to_step(matched, payload)
                else:
                    self._pending_evicted = payload
        elif event_type == "tool_end":
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
        elif event_type == "routing_decision" and isinstance(data, dict):
            tier = data.get("tier")
            if isinstance(tier, str):
                self._routing_tier = tier
        elif event_type == "privacy_level" and isinstance(data, dict):
            level = data.get("current_turn_level")
            if isinstance(level, str):
                self._privacy_level = level
        elif event_type == "privacy_route" and isinstance(data, dict):
            route = data.get("route")
            if isinstance(route, str):
                self._privacy_route = route
        elif event_type == "session_recording" and isinstance(data, dict):
            self._session_recording = string_keyed_dict(data)
        elif event_type == "clarification_required":
            clarification = collect_clarification_required(event)
            if clarification is not None:
                self._clarification = clarification
        elif event_type == "ui_update":
            subtype = event.get("subtype")
            if subtype == "ui_artifact" and isinstance(data, list):
                self._ui_artifacts.extend(string_keyed_dicts(data))
            elif subtype == "data_update" and isinstance(data, dict):
                surface_id = data.get("surface_id")
                updates = data.get("updates")
                if isinstance(surface_id, str) and isinstance(updates, dict):
                    merged_locally = False
                    for artifact in self._ui_artifacts:
                        if artifact.get("surface_id") == surface_id:
                            existing_data = artifact.get("data")
                            if isinstance(existing_data, dict):
                                artifact["data"] = deep_merge_ui_data(
                                    existing_data, updates
                                )
                            merged_locally = True
                            break
                    if not merged_locally and self._chat_id:
                        normalized_updates = string_keyed_dict(updates)
                        if normalized_updates is not None:
                            self._cross_turn_data_updates.append(
                                (surface_id, normalized_updates)
                            )
                            self._schedule_cross_turn_ui_patch(
                                surface_id, normalized_updates
                            )
        elif event_type == "status":
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
                    if (
                        phase_payload.get("phase") == "clarify"
                        and phase_payload.get("status") == "resolved"
                        and self._clarification is not None
                    ):
                        self._clarification = {
                            **self._clarification,
                            "answered": True,
                        }
            if step_key == "cache_break" and isinstance(data, dict):
                self._cache_break = data
            if isinstance(step_key, str) and step_key in _PERSISTED_STATUS_STEP_KEYS:
                step = {
                    "step_key": step_key,
                    "tool_name": event.get("tool_name"),
                    "items": event.get("items"),
                    "status": event.get("status"),
                }
                if isinstance(data, dict):
                    archive_restore_block = string_keyed_dict(
                        data.get("archive_restore_block")
                    )
                    if archive_restore_block is not None:
                        step["archive_restore_block"] = archive_restore_block
                    archive_restore_result = string_keyed_dict(
                        data.get("archive_restore_result")
                    )
                    if archive_restore_result is not None:
                        step["archive_restore_result"] = archive_restore_result
                self._progress_steps.append(step)

    @property
    def content(self) -> str:
        return "".join(self._content_parts)

    @property
    def reasoning(self) -> str | None:
        return "".join(self._reasoning_parts) if self._reasoning_parts else None

    @property
    def has_content(self) -> bool:
        return bool(self._content_parts) or bool(self._reasoning_parts)

    @property
    def has_persistable_turn(self) -> bool:
        """True when finalize should persist an assistant message row."""
        return self.has_content or self.extra_data is not None

    @property
    def sibling_group_id(self) -> str | None:
        return self._sibling_group_id

    @property
    def cross_turn_data_updates(self) -> list[tuple[str, dict[str, object]]]:
        return list(self._cross_turn_data_updates)

    def _flush_pending_evicted_ref(self) -> None:
        payload = self._pending_evicted
        if payload is None:
            return
        matched = _find_step_for_evicted(self._progress_steps, payload)
        if matched is not None:
            _attach_evicted_to_step(matched, payload)
            self._pending_evicted = None
            return
        tool_hint = payload.get("tool_name")
        fallback: dict[str, object] = {
            "tool_name": (
                tool_hint if isinstance(tool_hint, str) else _BASH_EXECUTE_TOOL
            ),
            "step_key": "bash_code_execute_tool_tool",
        }
        tool_call_id = payload.get("tool_call_id")
        if isinstance(tool_call_id, str) and tool_call_id.strip():
            fallback["tool_call_id"] = tool_call_id.strip()
        _attach_evicted_to_step(fallback, payload)
        self._progress_steps.append(fallback)
        self._pending_evicted = None

    @property
    def extra_data(self) -> dict[str, object] | None:
        """Build extra_data dict for DB storage. Returns None if empty."""
        result: dict[str, object] = {}
        if self._sources:
            result["sources"] = self._sources
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

        if hasattr(self, "_usage_alert") and self._usage_alert:
            result["usageAlert"] = self._usage_alert

        if self._model_name:
            result["modelName"] = self._model_name
        if self._token_economics:
            result["tokenEconomics"] = self._token_economics
        if self._routing_tier:
            result["routingTier"] = self._routing_tier
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
        if self._memory_retrieval_traces:
            result["memoryRetrievalTraces"] = self._memory_retrieval_traces
        if self._session_recording:
            result["sessionRecording"] = self._session_recording
        if self._clarification:
            result["clarification"] = self._clarification
        if self._plan_confirmation:
            result["planConfirmation"] = self._plan_confirmation
        if self._ui_artifacts:
            result["uiArtifacts"] = self._ui_artifacts
        if self._kanban_tasks_created:
            result["kanban_tasks_created"] = list(self._kanban_tasks_created)
        if self._cron_job_result is not None:
            result["cron_job_result"] = self._cron_job_result
        if self._file_mutation_failures:
            result["fileMutationFailures"] = list(self._file_mutation_failures)
        if self._council_phases:
            result["councilPhases"] = list(self._council_phases)
        if self.reasoning:
            result["reasoning"] = self.reasoning
            if self._reasoning_truncated:
                result["reasoningTruncated"] = True
                result["reasoningCharLimit"] = _MAX_REASONING_CHARS
        return result or None

    def _set_stop_reason(self, payload: dict[str, object]) -> None:
        normalized = _normalize_stop_reason(payload)
        if normalized is None:
            return
        if self._stop_reason is None:
            self._stop_reason = normalized
            return
        current_code = self._stop_reason.get("code")
        current_priority = (
            _stop_reason_priority(current_code) if isinstance(current_code, str) else 0
        )
        next_code = normalized.get("code")
        next_priority = (
            _stop_reason_priority(next_code) if isinstance(next_code, str) else 0
        )
        if next_priority >= current_priority:
            self._stop_reason = normalized

    def _extend_cited_memory_refs(self, refs: list[object]) -> None:
        seen = {
            str(ref.get("id"))
            for ref in self._cited_memory_refs
            if isinstance(ref.get("id"), str)
        }
        for ref in refs:
            if not isinstance(ref, dict):
                continue
            ref_id = ref.get("id")
            if not isinstance(ref_id, str) or not ref_id or ref_id in seen:
                continue
            normalized = {
                str(key): value for key, value in ref.items() if isinstance(key, str)
            }
            self._cited_memory_refs.append(normalized)
            seen.add(ref_id)

    def _append_memory_retrieval_trace(self, trace: dict[object, object]) -> None:
        trace_id = trace.get("id")
        if not isinstance(trace_id, str) or not trace_id:
            return
        if any(
            existing.get("id") == trace_id for existing in self._memory_retrieval_traces
        ):
            return
        normalized = {
            str(key): value for key, value in trace.items() if isinstance(key, str)
        }
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
