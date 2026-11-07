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
HITL clarification (`clarification`), plan confirmation (`planConfirmation`),
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

from app.services.agent.streaming_support.stream_collector_helpers import (
    collect_tool_stuck_pause,
    source_dedup_key,
    string_keyed_dict,
)

from .base import StreamCollectorBase
from .constants import _INTERRUPT_REPLAY_TYPES, _SSE_DATA_PREFIX
from .handlers import StreamEventHandlersMixin
from .state import StreamStateMixin

logger = logging.getLogger(__name__)


ACTIVE_COLLECTORS: dict[str, "StreamContentCollector"] = {}


def settle_tool_approvals_of(chat_id: str) -> None:
    """Take the answered tool-approval cards away from the run that is parked at them, if the chat has one.

    The run that answers a card leaves the parked run as the chat's collector until it registers a collector of its own.
    """
    parked_run = ACTIVE_COLLECTORS.get(chat_id)
    if parked_run is not None:
        parked_run.settle_tool_approvals()


class StreamContentCollector(StreamStateMixin, StreamEventHandlersMixin, StreamCollectorBase):
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
}
