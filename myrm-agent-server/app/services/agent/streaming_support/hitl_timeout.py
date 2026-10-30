"""HITL timeout auto-resume: arm a harness timer for a pending interrupt and run the resume when it fires.

[INPUT]
- myrm_agent_harness.agent.middlewares.approval.scheduler::ApprovalTimeoutScheduler (POS: per-chat timer and first-resolver arbitration)
- app.services.agent.turn_lease::server_turn_lease (POS: chat session claim + cancel token of a turn the server starts)
- app.services.agent.gateway::AgentBusyError, AgentDrainingError (POS: the chat is held by a live run, or the app drains)
- app.services.agent.streaming::ai_agent_service_stream (POS: gateway-managed agent run, imported lazily)
- app.services.agent.streaming_support.sse_helpers (POS: interrupt event detection)
- app.services.agent.streaming_support.stream_collector::StreamContentCollector (POS: persisted turn content; the chat's collector while the resumed run works)
- app.services.agent.stream_session.turn_end (POS: compaction drain, run digest close and lifecycle event, shared with a request's finalize)
- app.services.agent.stream_session.turn_history_sync::commit_run_history_sync (POS: records that the agent thread mirrors the stored chat once the turn completed)
- app.services.agent.stream_session.stream_finalize::assistant_turn_payload (POS: the stored form of a turn's answer, imported lazily)

[OUTPUT]
- CLARIFICATION_TIMEOUT_SECONDS / CLARIFICATION_NO_ANSWER_RESUME_VALUE: ask_question timeout and its empty answer
- arm_interrupt_timeout: arm the timer of the interrupt a run stopped at, or reopen one that has no timer
- schedule_approval_timeout / schedule_clarification_timeout: arm one interrupt kind
- HitlAnswerRecord: who settled a card (the user or the timeout default) and the resume value that settled it
- mark_pending_clarification_answered: flip the stored card to answered and keep the record on it (best effort)

[POS]
A turn that stops at an interrupt leaves a suspended graph; when nobody answers, the timer resumes it with the
timeout decision. The resumed run takes the chat under a server turn lease like any turn the server starts, so it
yields to a run that is already live and the chat Stop button and the emergency stop reach it. It also takes the chat's
collector from the run parked at the answered card, as a page-driven resume does: a page that reloads meanwhile attaches
to the resumed run, and the next card the run stops at is held by that run, where a reload and the turn state find it.
When it stops at the next interrupt it arms that interrupt's timer; an interrupt without a timer is reopened so its
manual answer is not refused as already resolved. When it ends without another interrupt it ends the turn the way a
request's finalize does: it stores the answer through the same builder, records the thread as in sync with the chat,
closes the run digest, announces the outcome to the lifecycle webhooks and gives the chat's collector up.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Literal, TypedDict

import orjson
from myrm_agent_harness.agent.middlewares.approval.scheduler import ApprovalTimeoutScheduler
from myrm_agent_harness.agent.streaming.run_digest import RunDigestPhase
from myrm_agent_harness.utils.coercion import parse_float

from app.services.agent.context_compaction_telemetry import enqueue_context_compaction_telemetry
from app.services.agent.gateway import AgentBusyError, AgentDrainingError
from app.services.agent.stream_session.turn_end import close_run_digest, schedule_compaction_drain
from app.services.agent.stream_session.turn_history_sync import commit_run_history_sync
from app.services.agent.streaming_support.sse_helpers import (
    clear_context_task_metrics,
    extract_approval_timeout,
    extract_clarification_required,
)
from app.services.agent.streaming_support.stream_collector import StreamContentCollector
from app.services.agent.turn_lease import server_turn_lease

if TYPE_CHECKING:
    from app.ai_agents import GeneralAgentParams

logger = logging.getLogger(__name__)

HitlKind = Literal["approval", "clarification"]


class HitlAnswerRecord(TypedDict):
    """How a card was settled, kept on the card so the transcript shows it after the card closes."""

    by: Literal["user", "timeout"]
    value: object


# Web structured clarify: auto-resume when user leaves the form open (OpenClaw default 900s).
CLARIFICATION_TIMEOUT_SECONDS = 900.0

# Empty dict is falsy in _on_ask_question and triggers best-judgment continuation.
CLARIFICATION_NO_ANSWER_RESUME_VALUE: dict[str, object] = {}

_DEFAULT_APPROVAL_TIMEOUT_SECONDS = 300.0

_DATA_PREFIX = "data: "


async def mark_pending_clarification_answered(chat_id: str, record: HitlAnswerRecord | None) -> None:
    """Flip the newest unanswered stored clarification of the chat to answered and keep ``record`` on it.

    The card lives on the persisted assistant row (a UUID minted at finalize), not on the
    request message id, which is bound to the user row. Best effort: a storage failure leaves the card
    open (a late click is refused as already resolved) instead of dropping the reply the run just produced.
    """
    from app.services.chat.chat_service import ChatService

    try:
        messages = await ChatService.get_all_messages(chat_id)
        for message in reversed(messages):
            if message.role != "assistant":
                continue
            extra_data = dict(message.extra_data or {})
            card = extra_data.get("clarification")
            if not isinstance(card, dict):
                continue
            if card.get("answered") is True:
                continue
            extra_data["clarification"] = {**card, "answered": True, **({"answerRecord": record} if record else {})}
            await ChatService.update_message_extra_data(message.id, extra_data)
            return
    except Exception:
        logger.warning("Failed to mark the answered clarification card: chat_id=%s", chat_id, exc_info=True)


def schedule_approval_timeout(
    chat_id: str,
    timeout_info: dict[str, object],
    params: GeneralAgentParams,
) -> None:
    """Register a backend timeout guard for a pending approval request."""
    _arm(
        chat_id,
        params,
        "approval",
        timeout_seconds=parse_float(
            timeout_info.get("seconds", _DEFAULT_APPROVAL_TIMEOUT_SECONDS), _DEFAULT_APPROVAL_TIMEOUT_SECONDS
        ),
        behavior=str(timeout_info.get("behavior", "deny")),
    )


def schedule_clarification_timeout(chat_id: str, params: GeneralAgentParams) -> None:
    """Register a backend timeout guard for a pending ask_question interrupt."""
    _arm(
        chat_id,
        params,
        "clarification",
        timeout_seconds=CLARIFICATION_TIMEOUT_SECONDS,
        behavior="deny",
        resume_value_override=CLARIFICATION_NO_ANSWER_RESUME_VALUE,
    )


def arm_interrupt_timeout(
    chat_id: str,
    params: GeneralAgentParams,
    *,
    approval_timeout: dict[str, object] | None,
    clarification_pending: bool,
    awaiting_answer: bool,
) -> None:
    """Arm the timer of the interrupt a run stopped at.

    An interrupt that carries no timer (plan confirmation, browser takeover) is reopened instead, so its
    manual answer is not refused as already resolved by an earlier interrupt of the same chat.
    """
    if clarification_pending:
        schedule_clarification_timeout(chat_id, params)
    elif approval_timeout:
        schedule_approval_timeout(chat_id, approval_timeout, params)
    elif awaiting_answer:
        ApprovalTimeoutScheduler.get().reopen(chat_id)


def _arm(
    chat_id: str,
    params: GeneralAgentParams,
    kind: HitlKind,
    *,
    timeout_seconds: float,
    behavior: str,
    resume_value_override: dict[str, object] | None = None,
) -> None:
    async def resume_callback(resume_value: dict[str, object]) -> None:
        await _resume_after_timeout(chat_id, params, resume_value, kind)

    ApprovalTimeoutScheduler.get().schedule(
        key=chat_id,
        timeout_seconds=timeout_seconds,
        behavior=behavior,
        resume_callback=resume_callback,
        resume_value_override=resume_value_override,
    )


async def _end_turn(chat_id: str, params: GeneralAgentParams, collector: StreamContentCollector, phase: RunDigestPhase) -> None:
    """End the turn a timer resumed, as a request's finalize ends it, unless the run stopped at another interrupt.

    A run that stopped at another interrupt stays the chat's collector, parked at its card. Otherwise the turn is over:
    left registered, the run would keep a reloading page attached to a stream that never ends, and the run digest would
    keep showing a run that is over. A newer run of the chat has replaced the registration by now and is left alone.
    """
    awaiting_answer = collector.has_pending_hitl_replay()
    try:
        schedule_compaction_drain(chat_id)
        enqueue_context_compaction_telemetry(chat_id)
        clear_context_task_metrics(chat_id)
        if awaiting_answer:
            return
        await commit_run_history_sync(chat_id, params.message_id, collector, interrupted=phase is not RunDigestPhase.COMPLETED)
        close_run_digest(
            chat_id,
            phase=phase,
            progress_steps=list(collector._progress_steps),
            agent_id=params.agent_id,
            was_cancelled=phase is RunDigestPhase.CANCELLED,
            had_fatal_error=False,
        )
    finally:
        if not awaiting_answer:
            collector.cleanup()


async def _resume_after_timeout(
    chat_id: str,
    params: GeneralAgentParams,
    resume_value: dict[str, object],
    kind: HitlKind,
) -> None:
    """Run the resume the fired timer decided on, persist its output, and arm the next interrupt's timer."""
    from langgraph.types import Command

    from app.services.agent.runtime_context import build_agent_runtime_context, resolve_stream_execution_mode
    from app.services.agent.streaming import ai_agent_service_stream
    from app.services.chat.chat_service import ChatService

    scheduler = ApprovalTimeoutScheduler.get()
    resume_params = params.model_copy()
    resume_params.query = Command(resume=resume_value)
    collector = StreamContentCollector()
    extra_context: dict[str, object] = {}
    next_approval_timeout: dict[str, object] | None = None
    clarification_pending = False
    parked_run: StreamContentCollector | None = None
    phase = RunDigestPhase.COMPLETED
    turn_over = False
    try:
        try:
            # A message id keys the cancel token; the original turn's token is gone by the time a timer fires.
            async with server_turn_lease(chat_id, params.message_id or f"hitl-resume-{chat_id}") as cancel_token:
                turn_over = True
                # The answered card must not stay where a reloading page finds it. Taken only once the lease is held: a refused
                # run answered nothing.
                parked_run = collector.take_over_chat(chat_id)
                # What a page-driven resume reads: the stored history now holds the user message that opened the turn, whose
                # [use ...] tag is how a resume finds the turn's skill hooks. The params captured when the card appeared
                # hold the history from before that message.
                resume_params.chat_history = await ChatService.load_web_chat_history(chat_id)
                extra_context = await build_agent_runtime_context(execution_mode=resolve_stream_execution_mode())
                async for chunk in ai_agent_service_stream(
                    params=resume_params, cancel_token=cancel_token, extra_context=extra_context
                ):
                    sse_line = (
                        f"{_DATA_PREFIX}{orjson.dumps(chunk).decode('utf-8')}\n\n" if isinstance(chunk, dict) else str(chunk)
                    )
                    collector.feed_sse(sse_line)
                    next_approval_timeout = extract_approval_timeout(sse_line) or next_approval_timeout
                    clarification_pending = clarification_pending or extract_clarification_required(sse_line)
                if cancel_token.is_cancelled:
                    phase = RunDigestPhase.CANCELLED
        except asyncio.CancelledError:
            phase = RunDigestPhase.CANCELLED
            raise
        except Exception as exc:
            # The answer was not consumed by a finished run: the chat goes back to the parked run, which still holds the card, and
            # the turn is not over, so a manual answer has something to answer. Refused because a live run owns the chat, that
            # run arms its own interrupt.
            scheduler.reopen(chat_id)
            collector.hand_chat_back(parked_run)
            turn_over = False
            if isinstance(exc, AgentBusyError | AgentDrainingError):
                logger.warning("HITL timeout resume skipped: chat_id=%s, reason=%s", chat_id, exc)
                return
            raise

        try:
            # Mark before persisting: the continuation may carry a new unanswered card that must stay unanswered.
            timeout_record: HitlAnswerRecord = {"by": "timeout", "value": resume_value}
            if kind == "clarification":
                await mark_pending_clarification_answered(chat_id, timeout_record)

            if collector.has_persistable_turn:
                from app.services.agent.stream_session.stream_finalize import assistant_turn_payload

                content, extra_data = assistant_turn_payload(collector, chat_id, extra_context=extra_context, stream_ttft_ms=None)
                await ChatService.persist_assistant_message_safe(
                    chat_id,
                    content,
                    extra_data=extra_data,
                    timezone=resume_params.timezone,
                    request_message_id=resume_params.message_id,
                )
        finally:
            # The run already stopped: whatever the bookkeeping above did, the next interrupt must stay answerable.
            arm_interrupt_timeout(
                chat_id,
                resume_params,
                approval_timeout=next_approval_timeout,
                clarification_pending=clarification_pending,
                awaiting_answer=collector.has_pending_hitl_replay(),
            )
    finally:
        if turn_over:
            await _end_turn(chat_id, resume_params, collector, phase)
    logger.info("HITL timeout auto-resume completed: kind=%s, chat_id=%s", kind, chat_id)
