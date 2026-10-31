"""SSE stream content collector for persisting assistant messages with metadata.

[INPUT]
JSON SSE chunks and parsed Agent stream events (POS: Agent runtime event stream)
- stream_collector_helpers (POS: stateless SSE event parsing helpers)
- app.core.agent.stop_reason (POS: stored shape of a stop reason, and which reason is kept)
- evicted_output (POS: evicted tool output references matched to progress steps)
- myrm_agent_harness.toolkits.code_execution.executors.models::scrub_sensitive_info
  (POS: Harness-level sensitive token/path scrubbing)
- myrm_agent_harness.utils.text_sanitizer::sanitize_llm_output
  (POS: LLM raw text sanitizer for control/sentinel cleanup)

[OUTPUT]
StreamContentCollector: collects assistant content and message extra_data, including memory citation refs,
retrieval traces, end-to-end stream TTFT (`streamTtftMs`), kanban_tasks_created, cron_job_result,
HITL clarification (`clarification`), deep-research plan confirmation (`planConfirmation`),
file mutation failures (`fileMutationFailures`), council phase progress (`councilPhases`),
reasoning safety metadata (`reasoningTruncated` / `reasoningCharLimit`),
per-stream evicted output references (`evicted_file_ref` for stdout, `evicted_stderr_file_ref` for stderr,
with stored_chars/total_lines/storage_truncated metrics for each),
and deduplicated model-failover progress steps (`model_failover*`) from STATUS + SSE channels,
and `citationAudit` when inline 【N】 markers are present alongside collected sources,
and a loop guard pause (`tool_stuck`): saved as a `tool_stuck_paused` progress step and reported through
`tool_stuck_paused`, not held as an interrupt card nobody can answer.

[POS]
Agent API persistence helper. Converts transient SSE events into durable Message.extra_data metadata;
each event type is handled by one `_on_<event type>` method, found through `_EVENT_HANDLERS`.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable

from myrm_agent_harness.agent.streaming.answer_draft import AnswerDraft
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
    parse_evicted_ref_payload,
    step_accepts_pending_evicted,
)
from app.services.agent.streaming_support.stream_collector_helpers import (
    collect_clarification_required,
    collect_cron_job_result,
    collect_file_mutation_failures,
    collect_kanban_task_created,
    collect_plan_confirmation_status,
    collect_tool_stuck_pause,
    is_memory_citation_tool,
    iteration_limit_message,
    merge_sources_list,
    merge_tasks_step,
    source_dedup_key,
    string_keyed_dict,
    string_keyed_dicts,
)
from app.services.skills.mutation_batch_stream import link_batch_to_step

_SSE_DATA_PREFIX = "data: "
_MAX_REASONING_CHARS = 24_000
_PERSISTED_STATUS_STEP_KEYS = frozenset({"archive_restore_blocked", "archive_restore_result"})
_FAILOVER_REASON_TO_STEP_KEY: dict[str, str] = {
    "rate_limit": "model_failover_rate_limit",
    "overloaded": "model_failover_overloaded",
    "timeout": "model_failover_timeout",
    "billing": "model_failover_billing",
    "context_overflow": "model_failover_context_overflow",
    "response_format": "model_failover_response_format_error",
    "format": "model_failover_response_format_error",
    "model_not_found": "model_failover_model_not_found",
    "auth_permanent": "model_failover_auth",
    "session_expired": "model_failover_auth",
    "safety_block": "safety_fallback_active",
}
logger = logging.getLogger(__name__)


ACTIVE_COLLECTORS: dict[str, "StreamContentCollector"] = {}


def settle_tool_approvals_of(chat_id: str) -> None:
    """Take the answered tool-approval cards away from the run that is parked at them, if the chat has one.

    The run that answers a card leaves the parked run as the chat's collector until it registers a collector of its own.
    """
    parked_run = ACTIVE_COLLECTORS.get(chat_id)
    if parked_run is not None:
        parked_run.settle_tool_approvals()


def _sync_run_digest(collector: "StreamContentCollector") -> None:
    chat_id = collector._chat_id
    if not chat_id:
        return
    from app.services.copilot.run_digest_store import RunDigestStore

    RunDigestStore.update_from_progress(chat_id, collector._progress_steps)


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

    def __init__(self, sibling_group_id: str | None = None, chat_id: str | None = None) -> None:
        self._message_id: str | None = None
        self._answer = AnswerDraft()
        self._reasoning_parts: list[str] = []
        self._reasoning_char_count = 0
        self._reasoning_truncated = False
        self._sources: list[dict[str, object]] = []
        self._progress_steps: list[dict[str, object]] = []
        self._cited_memory_ids: list[str] = []
        self._cited_memory_refs: list[dict[str, object]] = []
        self._turn_loaded_skills: list[dict[str, object]] = []
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
        self._routing_reason: str | None = None
        self._privacy_level: str | None = None
        self._privacy_route: str | None = None
        self._cache_break: dict[str, object] | None = None
        self._token_economics: dict[str, object] | None = None
        self._usage_alert: dict[str, object] | None = None
        self._session_recording: dict[str, object] | None = None
        self._clarification: dict[str, object] | None = None
        self._plan_confirmation: dict[str, object] | None = None
        self._pending_interrupt_events: list[dict[str, object]] = []
        self._tool_stuck_paused = False
        self._kanban_tasks_created: list[dict[str, object]] = []
        self._cron_job_result: dict[str, object] | None = None
        self._file_mutation_failures: list[dict[str, object]] = []
        self._council_phases: list[dict[str, object]] = []
        self._staged_artifacts: list[dict[str, object]] = []
        self._deliverable_tier: dict[str, object] | None = None
        self._pending_evicted: list[dict[str, object]] = []
        self._sibling_group_id: str | None = sibling_group_id
        self._tool_result_details: dict[str, object] | None = None
        self._chat_id: str | None = chat_id
        self._subscribers: list[asyncio.Queue[dict[str, object]]] = []

        if self._chat_id:
            ACTIVE_COLLECTORS[self._chat_id] = self

    def has_pending_hitl_replay(self) -> bool:
        """True when attach subscribers may still need interrupt replay."""
        return bool(self._pending_interrupt_events)

    def has_pending_tool_approval(self) -> bool:
        """True while the turn is parked behind a tool-approval card that only this collector can hand back to a new page.

        A clarification is stored with the message and an ``approval_required`` card has its registry record; a tool-approval card
        has neither, so a page that reloads while the turn waits gets it again only by replaying the collector's events.
        """
        return any(event.get("type") == "tool_approval_request" for event in self._pending_interrupt_events)

    def settle_tool_approvals(self) -> None:
        """Forget the tool-approval cards once they are answered.

        The parked run stays the chat's collector while the answered run starts (about a second for a resume the user sent):
        a page that attaches in that time would otherwise get the card back and offer an answer that is already taken.
        """
        self._pending_interrupt_events = [
            event for event in self._pending_interrupt_events if event.get("type") != "tool_approval_request"
        ]

    def take_over_chat(self, chat_id: str) -> "StreamContentCollector | None":
        """Become the chat's collector for a run that answers the card its parked run holds, and return the run it replaces.

        From now on a page that attaches or reloads gets this run: its snapshot, its live events, and the card it stops at
        (the parked run's card is answered). The replaced run's attached pages end when the registry no longer names it.
        """
        replaced = ACTIVE_COLLECTORS.get(chat_id)
        self._chat_id = chat_id
        ACTIVE_COLLECTORS[chat_id] = self
        return replaced

    def hand_chat_back(self, replaced: "StreamContentCollector | None") -> None:
        """Give the chat back to the run this one replaced: this run failed before it consumed the answer.

        A run that took the chat meanwhile keeps it.
        """
        self.cleanup()
        if replaced is not None and self._chat_id:
            ACTIVE_COLLECTORS.setdefault(self._chat_id, replaced)

    @property
    def tool_stuck_paused(self) -> bool:
        """True when the loop guard paused the turn: it has no card to answer, so the turn is over."""
        return self._tool_stuck_paused

    @property
    def message_id(self) -> str | None:
        """The messageId of the assistant message being collected."""
        return self._message_id

    def mark_stream_completion_error(self) -> None:
        """Mark the persisted turn as errored (no message_end ever arrives).

        When the stream dies on a fatal exception the normal ``message_end``
        event (which carries ``completion_status``) never fires; this lets the
        finalize path persist ``completionStatus=error`` so API consumers stop
        treating the turn as still streaming.
        """
        self._completion_status = "error"

    def mark_stream_completion_cancelled(self) -> None:
        """Mark the persisted turn as cancelled when the stream task is cancelled before ``message_end``."""
        self._completion_status = "cancelled"

    def cleanup(self) -> None:
        """Remove from active collectors registry."""
        if self._chat_id and ACTIVE_COLLECTORS.get(self._chat_id) is self:
            del ACTIVE_COLLECTORS[self._chat_id]

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
        merged_sources_dict: dict[str, dict[str, object]] = {}
        ordered_sources: list[dict[str, object]] = []
        for source in self._sources:
            key = source_dedup_key(source)
            if key not in merged_sources_dict:
                merged_sources_dict[key] = source.copy()
                ordered_sources.append(merged_sources_dict[key])
            else:
                merged_sources_dict[key].update(source)

        return {
            "content": self._answer.text,
            "reasoning": "".join(self._reasoning_parts),
            "progress_steps": list(self._progress_steps),
            "sources": ordered_sources,
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
            event = string_keyed_dict(json.loads(chunk[len(_SSE_DATA_PREFIX) :].rstrip()))
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
        if collect_tool_stuck_pause(self._progress_steps, event):
            self._tool_stuck_paused = True
        elif isinstance(event_type, str) and event_type in _INTERRUPT_REPLAY_TYPES:
            self._pending_interrupt_events.append(event)
        data = event.get("data")

        if self._message_id is None:
            raw_mid = event.get("messageId")
            if isinstance(raw_mid, str) and raw_mid:
                self._message_id = raw_mid

        self._answer.feed(event)
        handler = _EVENT_HANDLERS.get(event_type) if isinstance(event_type, str) else None
        if handler is not None:
            handler(self, event, data)

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
                if (
                    phase_payload.get("phase") == "clarify"
                    and phase_payload.get("status") == "resolved"
                    and self._clarification is not None
                ):
                    answer_record = phase_payload.get("answerRecord")
                    self._clarification = {
                        **self._clarification,
                        "answered": True,
                        **({"answerRecord": answer_record} if isinstance(answer_record, dict) else {}),
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

    def _on_model_escalated(self, event: dict[str, object], data: object) -> None:
        if not isinstance(data, dict):
            return
        # Escalation clears the turn and re-plays it with a stronger model;
        # any text containing the escalation marker is a draft to drop.
        self._discard_draft()
        from_model = data.get("from_model")
        to_model = data.get("to_model")
        label_parts = [str(v) for v in (from_model, to_model) if v]
        self._progress_steps.append(
            {
                "step_key": "model_escalated",
                "items": [{"text": " → ".join(label_parts)}] if label_parts else [],
                "status": "success",
            }
        )

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
        (model failover, transient retry, context compaction, escalation, ...)
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


_EVENT_HANDLERS: dict[str, Callable[[StreamContentCollector, dict[str, object], object], None]] = {
    "iteration_limit_reached": StreamContentCollector._on_iteration_limit_reached,
    "engine_limit_reached": StreamContentCollector._on_engine_limit_reached,
    "agent_cancelled": StreamContentCollector._on_agent_cancelled,
    "error": StreamContentCollector._on_error,
    "reasoning": StreamContentCollector._on_reasoning,
    "sources": StreamContentCollector._on_sources,
    "file_mutation_failed": StreamContentCollector._on_file_mutation_failed,
    "council_phase": StreamContentCollector._on_council_phase,
    "tasks_steps": StreamContentCollector._on_tasks_steps,
    "token_usage": StreamContentCollector._on_token_usage,
    "message_end": StreamContentCollector._on_message_end,
    "tool_stdout_chunk": StreamContentCollector._on_tool_stdout_chunk,
    "tool_evicted_ref": StreamContentCollector._on_tool_evicted_ref,
    "tool_end": StreamContentCollector._on_tool_end,
    "routing_decision": StreamContentCollector._on_routing_decision,
    "privacy_level": StreamContentCollector._on_privacy_level,
    "privacy_route": StreamContentCollector._on_privacy_route,
    "session_recording": StreamContentCollector._on_session_recording,
    "clarification_required": StreamContentCollector._on_clarification_required,
    "status": StreamContentCollector._on_status,
    "model_failover": StreamContentCollector._on_model_failover,
    "model_escalated": StreamContentCollector._on_model_escalated,
}
