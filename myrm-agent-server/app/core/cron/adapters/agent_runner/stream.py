"""Cron Agent 流式消费与结果累积。

[POS]
agent_runner 的流处理层：把 Agent 事件累加成 JobResult，不参与任务编排。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from myrm_agent_harness.agent.streaming.answer_draft import AnswerDraft
from myrm_agent_harness.core.security.audit import get_audit_entries
from myrm_agent_harness.toolkits.cron.types import (
    CronJob,
    JobResult,
    SessionTarget,
)

from app.core.agent.stop_reason import merge_stop_reason

from ..blocked_actions import blocked_actions_metadata
from ..effectful_steps import has_effectful_tools
from ..failure_recoverability import is_transient_failure
from ..provider_window_deferral import usage_limit_deferral
from .support import _coerce_usage_int, _derive_stop_reason_from_event, _source_sort_key

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


def _timeout_result(job: CronJob) -> JobResult:
    """The run used up its time budget; a repeat would spend the same budget again, so it is never repeated."""
    timeout = job.timeout_seconds or 300
    logger.warning("Cron agent job %s timed out after %ds", job.id, timeout)
    return JobResult(success=False, error=f"agent timed out after {timeout}s", retry_safe=False)


def _deterministic_failure(error: str) -> JobResult:
    """A gate turned the job away (no prompt, one-shot budget, prompt scan, workflow template); a repeat meets it again."""
    return JobResult(success=False, error=error, retry_safe=False)


def _failure_result(job: CronJob, exc: Exception, acc: _StreamAccumulator) -> JobResult:
    """Map an exception escaping an agent run to its JobResult (breaker, usage-limit deferral, failure)."""
    from myrm_agent_harness.agent.errors import RunawayCircuitBreakException

    if isinstance(exc, RunawayCircuitBreakException):
        logger.error("Cron agent job %s tripped RunawayCircuitBreakException: %s", job.id, exc)
        return JobResult(
            success=False,
            error=str(exc),
            circuit_broken=True,
        )
    deferral = usage_limit_deferral(exc)
    if deferral is not None:
        logger.warning("Cron agent job %s hit a provider usage limit: %s", job.id, exc)
        return deferral
    logger.warning("Cron agent job %s failed: %s", job.id, exc)
    return JobResult(success=False, error=str(exc), retry_safe=not acc.effectful and is_transient_failure(exc))


# ---------------------------------------------------------------------------
# Stream accumulation
# ---------------------------------------------------------------------------


@dataclass
class _StreamAccumulator:
    answer: AnswerDraft = field(default_factory=AnswerDraft)
    progress_steps: list[dict[str, object]] = field(default_factory=list)
    sources: list[dict[str, object]] = field(default_factory=list)
    usage: dict[str, int] | None = None
    error: str | None = None
    stop_reason: dict[str, object] | None = None
    circuit_broken: bool = False
    # A workflow step began: its nodes may already have acted, and the workflow stream names no tools.
    workflow_step_ran: bool = False
    _seen_indices: set[int] = field(default_factory=set)

    @property
    def effectful(self) -> bool:
        """A step issued a state-changing call (send, write, pay).

        It may already have taken effect and survives a failure of the run, so a repeat could do it again.
        """
        return self.workflow_step_ran or has_effectful_tools(self.progress_steps)

    def add_sources(self, items: list[dict[str, object]]) -> None:
        for src in items:
            idx = src.get("index")
            if isinstance(idx, int) and idx not in self._seen_indices:
                self._seen_indices.add(idx)
                self.sources.append(src)

    def to_result(self, model: str | None = None) -> JobResult:
        output = self.answer.text
        metadata: dict[str, object] = {}
        if self.progress_steps:
            metadata["progressSteps"] = self.progress_steps
        if self.stop_reason:
            metadata["stopReason"] = self.stop_reason
        if self.sources:
            metadata["sources"] = sorted(self.sources, key=_source_sort_key)
        if model:
            metadata["model"] = model
        if self.usage:
            metadata["usage"] = self.usage

        metadata.update(blocked_actions_metadata(get_audit_entries()))

        if self.error or self.circuit_broken:
            return JobResult(
                success=False,
                output=output,
                error=self.error or "Runaway circuit break triggered",
                metadata=metadata or None,
                circuit_broken=self.circuit_broken,
                retry_safe=not self.effectful,
            )

        # Also set on success: a later verification step can still turn this result into a failure.
        return JobResult(
            success=True,
            output=output or "agent completed",
            metadata=metadata or None,
            retry_safe=not self.effectful,
        )

    def set_stop_reason(self, payload: dict[str, object]) -> None:
        self.stop_reason = merge_stop_reason(self.stop_reason, payload)


async def _load_thread_history(job: CronJob) -> list[list[str | object]] | None:
    """Load chat history when session_target is MAIN and chat_id is available."""
    if job.session_target != SessionTarget.MAIN or not job.chat_id:
        return None
    try:
        from app.services.chat.chat_service import ChatService

        history = await ChatService.load_web_chat_history(
            chat_id=job.chat_id,
            max_messages=30,
        )
        if history:
            logger.debug(
                "Cron job %s: loaded %d history entries from chat %s",
                job.id,
                len(history),
                job.chat_id,
            )
        # The agent entry point types history entries loosely; re-wrap so the invariant list types line up.
        return [list(entry) for entry in history]
    except Exception:
        logger.warning(
            "Cron job %s: failed to load thread history for chat %s",
            job.id,
            job.chat_id,
        )
        return None


async def _consume_stream(
    agent: object,
    job: CronJob,
    effective_prompt: str,
    runtime_context: dict[str, object],
    acc: _StreamAccumulator,
    *,
    untrusted: bool,
) -> JobResult:
    from app.ai_agents.general_agent import GeneralAgent

    assert isinstance(agent, GeneralAgent)

    model_name: str | None = getattr(agent.model_cfg, "model", None)
    # The bound thread is the owner's private conversation; a non-owner's run never reads it.
    chat_history = None if untrusted else await _load_thread_history(job)

    async for event in agent.process_stream(
        query=effective_prompt,
        chat_history=chat_history,
        chat_id=job.chat_id,
        context=runtime_context,
    ):
        event_type = event.get("type", "")
        stop_reason = _derive_stop_reason_from_event(event)
        if stop_reason is not None:
            acc.set_stop_reason(stop_reason)

        acc.answer.feed(event)
        if event_type == "message_end" and isinstance(event.get("usage"), dict):
            raw_u = event.get("usage")
            assert isinstance(raw_u, dict)
            acc.usage = {str(k): _coerce_usage_int(v) for k, v in raw_u.items()}
        elif event_type == "error":
            error_msg = event.get("error", "unknown agent error")
            error_type = event.get("error_type", "")
            acc.error = f"{error_type}: {error_msg}" if error_type else str(error_msg)
            if "RUNAWAY_CIRCUIT_BREAKER" in str(error_msg) or "RunawayCircuitBreakException" in str(error_type):
                acc.circuit_broken = True
        elif event_type == "tasks_steps":
            acc.progress_steps.append(
                {
                    "step_key": event.get("step_key"),
                    "tool_name": event.get("tool_name"),
                    "items": event.get("data"),
                    "count": event.get("count"),
                    "error": (event.get("error") if event.get("status") == "error" else None),
                }
            )
        elif event_type == "sources" and isinstance(event.get("data"), list):
            raw_list = event.get("data")
            assert isinstance(raw_list, list)
            src_items: list[dict[str, object]] = []
            for el in raw_list:
                if isinstance(el, dict):
                    src_items.append({str(k): val for k, val in el.items()})
            acc.add_sources(src_items)

    return acc.to_result(model=model_name)


async def _consume_dynamic_workflow_stream(
    stream: object,
    job: CronJob,
    model_name: str | None,
    acc: _StreamAccumulator,
) -> JobResult:
    from collections.abc import AsyncIterable

    assert isinstance(stream, AsyncIterable)

    async for event in stream:
        if not isinstance(event, dict):
            continue
        event_type = event.get("type", "")
        stop_reason = _derive_stop_reason_from_event(event)
        if stop_reason is not None:
            acc.set_stop_reason(stop_reason)

        acc.answer.feed(event)
        if event_type == "message_end" and isinstance(event.get("usage"), dict):
            raw_u = event.get("usage")
            assert isinstance(raw_u, dict)
            acc.usage = {str(k): _coerce_usage_int(v) for k, v in raw_u.items()}
        elif event_type == "error":
            error_msg = event.get("error", "unknown agent error")
            error_type = event.get("error_type", "")
            acc.error = f"{error_type}: {error_msg}" if error_type else str(error_msg)
            if "RUNAWAY_CIRCUIT_BREAKER" in str(error_msg) or "RunawayCircuitBreakException" in str(error_type):
                acc.circuit_broken = True
        elif event_type == "status":
            data = event.get("data")
            if isinstance(data, dict):
                step_key = data.get("step_key") or data.get("phase")
                if isinstance(step_key, str):
                    acc.workflow_step_ran = True
                    acc.progress_steps.append(
                        {
                            "step_key": step_key,
                            "tool_name": None,
                            "items": data,
                            "count": None,
                            "error": None,
                        }
                    )
        elif event_type == "sources" and isinstance(event.get("data"), list):
            raw_list = event.get("data")
            assert isinstance(raw_list, list)
            src_items: list[dict[str, object]] = []
            for el in raw_list:
                if isinstance(el, dict):
                    src_items.append({str(k): val for k, val in el.items()})
            acc.add_sources(src_items)

    return acc.to_result(model=model_name)
