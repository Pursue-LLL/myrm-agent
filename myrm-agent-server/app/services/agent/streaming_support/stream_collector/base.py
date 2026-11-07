"""流式收集器的共享状态声明。

[POS]
handlers 与 state 两个 mixin 共用的实例属性类型，集中一处避免重复注解。
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from myrm_agent_harness.agent.streaming.answer_draft import AnswerDraft


class StreamCollectorBase:
    """实例状态由 StreamContentCollector.__init__ 建立。"""

    _message_id: str | None
    _answer: AnswerDraft
    _reasoning_char_count: int
    _reasoning_truncated: bool
    _tool_stuck_paused: bool
    _reasoning_parts: list[str]
    _sources: list[dict[str, object]]
    _progress_steps: list[dict[str, object]]
    _cited_memory_ids: list[str]
    _cited_memory_refs: list[dict[str, object]]
    _turn_loaded_skills: list[dict[str, object]]
    _memory_retrieval_traces: list[dict[str, object]]
    _usage: dict[str, object] | None
    _context_budget: dict[str, object] | None
    _cost_usd: float | None
    _cost_status: str | None
    _completion_status: str | None
    _stream_ttft_ms: int | None
    _stop_reason: dict[str, object] | None
    _model_name: str | None
    _routing_tier: str | None
    _routing_reason: str | None
    _privacy_level: str | None
    _privacy_route: str | None
    _cache_break: dict[str, object] | None
    _token_economics: dict[str, object] | None
    _usage_alert: dict[str, object] | None
    _session_recording: dict[str, object] | None
    _clarification: dict[str, object] | None
    _plan_confirmation: dict[str, object] | None
    _pending_interrupt_events: list[dict[str, object]]
    _kanban_tasks_created: list[dict[str, object]]
    _cron_job_result: dict[str, object] | None
    _file_mutation_failures: list[dict[str, object]]
    _council_phases: list[dict[str, object]]
    _staged_artifacts: list[dict[str, object]]
    _deliverable_tier: dict[str, object] | None
    _pending_evicted: list[dict[str, object]]
    _sibling_group_id: str | None
    _tool_result_details: dict[str, object] | None
    _chat_id: str | None
    _subscribers: list[asyncio.Queue[dict[str, object]]]

    # 跨 mixin 调用：实现分别位于 state.py / core.py，此处只声明签名。
    def _discard_draft(self) -> None: ...
    def _append_failover_step(self, step_key: str, item_text: str) -> None: ...
    def _append_memory_retrieval_trace(self, trace: dict[object, object]) -> None: ...
    def _append_reasoning(self, chunk: str) -> None: ...
    def _extend_cited_memory_refs(self, refs: list[object]) -> None: ...
    def _flush_pending_evicted_ref(self) -> None: ...
    def _set_stop_reason(self, payload: dict[str, object]) -> None: ...
    def mark_stream_completion_cancelled(self) -> None: ...
