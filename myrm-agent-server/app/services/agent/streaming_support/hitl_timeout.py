"""HITL timeout auto-resume: arm a harness timer for a pending interrupt and run the resume when it fires.

[INPUT]
- myrm_agent_harness.agent.middlewares.approval.scheduler::ApprovalTimeoutScheduler (POS: per-chat timer and first-resolver arbitration)
- app.services.agent.gateway::get_agent_gateway (POS: chat session reservation shared with user turns)
- app.services.agent.streaming::ai_agent_service_stream (POS: gateway-managed agent run, imported lazily)
- app.services.agent.streaming_support.sse_helpers (POS: interrupt event detection)
- app.services.agent.streaming_support.stream_collector::StreamContentCollector (POS: persisted turn content)

[OUTPUT]
- CLARIFICATION_TIMEOUT_SECONDS / CLARIFICATION_NO_ANSWER_RESUME_VALUE: ask_question timeout and its empty answer
- DIRECTORY_TIMEOUT_SECONDS / DIRECTORY_DENY_RESUME_VALUE: request_directory timeout and its denial
- arm_interrupt_timeout: arm the timer of the interrupt a run stopped at, or reopen one that has no timer
- schedule_approval_timeout / schedule_clarification_timeout / schedule_directory_timeout: arm one interrupt kind
- mark_pending_clarification_answered / mark_pending_directory_request_answered: flip the stored card to answered

[POS]
A turn that stops at an interrupt leaves a suspended graph; when nobody answers, the timer resumes it with the
timeout decision. The resumed run goes through the same gateway as a user turn, so it reserves the chat first and
yields to a run that is already live. When it stops at the next interrupt it arms that interrupt's timer; an
interrupt without a timer is reopened so its manual answer is not refused as already resolved.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Literal

import orjson
from myrm_agent_harness.agent.middlewares.approval.scheduler import ApprovalTimeoutScheduler
from myrm_agent_harness.utils.coercion import parse_float

from app.services.agent.gateway import AgentBusyError, AgentDrainingError, get_agent_gateway
from app.services.agent.streaming_support.sse_helpers import (
    extract_approval_timeout,
    extract_clarification_required,
    extract_directory_request_required,
)
from app.services.agent.streaming_support.stream_collector import StreamContentCollector

if TYPE_CHECKING:
    from app.ai_agents import GeneralAgentParams

logger = logging.getLogger(__name__)

HitlKind = Literal["approval", "clarification", "directory"]

# Web structured clarify: auto-resume when user leaves the form open (OpenClaw default 900s).
CLARIFICATION_TIMEOUT_SECONDS = 900.0

# Empty dict is falsy in _on_ask_question and triggers best-judgment continuation.
CLARIFICATION_NO_ANSWER_RESUME_VALUE: dict[str, object] = {}

# request_directory HITL: auto-deny when user leaves the card open (parity with clarify).
DIRECTORY_TIMEOUT_SECONDS = CLARIFICATION_TIMEOUT_SECONDS
DIRECTORY_DENY_RESUME_VALUE: dict[str, object] = {"granted": False}

_DEFAULT_APPROVAL_TIMEOUT_SECONDS = 300.0

_DATA_PREFIX = "data: "


async def _mark_latest_unanswered(chat_id: str, card_key: str) -> None:
    """Flip the newest stored ``card_key`` card of the chat from unanswered to answered.

    The card lives on the persisted assistant row (a UUID minted at finalize), not on the
    request message id, which is bound to the user row.
    """
    from app.services.chat.chat_service import ChatService

    messages = await ChatService.get_all_messages(chat_id)
    for message in reversed(messages):
        if message.role != "assistant":
            continue
        extra_data = dict(message.extra_data or {})
        card = extra_data.get(card_key)
        if not isinstance(card, dict):
            continue
        if card.get("answered") is True:
            continue
        extra_data[card_key] = {**card, "answered": True}
        await ChatService.update_message_extra_data(message.id, extra_data)
        return


async def mark_pending_clarification_answered(chat_id: str) -> None:
    """Mark the latest assistant clarification as answered after a successful resume."""
    await _mark_latest_unanswered(chat_id, "clarification")


async def mark_pending_directory_request_answered(chat_id: str) -> None:
    """Mark the latest assistant directoryRequest as answered after resume."""
    await _mark_latest_unanswered(chat_id, "directoryRequest")


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


def schedule_directory_timeout(chat_id: str, params: GeneralAgentParams) -> None:
    """Register a backend timeout guard for a pending request_directory interrupt."""
    _arm(
        chat_id,
        params,
        "directory",
        timeout_seconds=DIRECTORY_TIMEOUT_SECONDS,
        behavior="deny",
        resume_value_override=DIRECTORY_DENY_RESUME_VALUE,
    )


def arm_interrupt_timeout(
    chat_id: str,
    params: GeneralAgentParams,
    *,
    approval_timeout: dict[str, object] | None,
    clarification_pending: bool,
    directory_pending: bool,
    awaiting_answer: bool,
) -> None:
    """Arm the timer of the interrupt a run stopped at.

    An interrupt that carries no timer (plan confirmation, browser takeover) is reopened instead, so its
    manual answer is not refused as already resolved by an earlier interrupt of the same chat.
    """
    if clarification_pending:
        schedule_clarification_timeout(chat_id, params)
    elif directory_pending:
        schedule_directory_timeout(chat_id, params)
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
    gateway = get_agent_gateway()
    try:
        gateway.reserve_session(chat_id, active_message_id=params.message_id)
    except (AgentBusyError, AgentDrainingError) as exc:
        # The live run owns the suspended graph and arms its own interrupt when it stops.
        scheduler.reopen(chat_id)
        logger.warning("HITL timeout resume skipped: chat_id=%s, reason=%s", chat_id, exc)
        return

    resume_params = params.model_copy()
    resume_params.query = Command(resume=resume_value)
    collector = StreamContentCollector()
    next_approval_timeout: dict[str, object] | None = None
    clarification_pending = False
    directory_pending = False
    try:
        extra_context = await build_agent_runtime_context(execution_mode=resolve_stream_execution_mode())
        async for chunk in ai_agent_service_stream(params=resume_params, extra_context=extra_context):
            sse_line = f"{_DATA_PREFIX}{orjson.dumps(chunk).decode('utf-8')}\n\n" if isinstance(chunk, dict) else str(chunk)
            collector.feed_sse(sse_line)
            next_approval_timeout = extract_approval_timeout(sse_line) or next_approval_timeout
            clarification_pending = clarification_pending or extract_clarification_required(sse_line)
            directory_pending = directory_pending or extract_directory_request_required(sse_line)
    except Exception:
        # The suspended graph was not consumed by a finished run: let a manual answer through.
        scheduler.reopen(chat_id)
        raise
    finally:
        # The run releases its own reservation once the stream took it over; this only clears a reservation that never reached the stream.
        gateway.release_if_reserved_only(chat_id)

    try:
        # Mark before persisting: the continuation may carry a new unanswered card that must stay unanswered.
        if kind == "clarification":
            await mark_pending_clarification_answered(chat_id)
        elif kind == "directory":
            await mark_pending_directory_request_answered(chat_id)

        if collector.has_content:
            await ChatService.persist_assistant_message_safe(
                chat_id,
                collector.content,
                extra_data=collector.extra_data,
                request_message_id=resume_params.message_id,
            )
    finally:
        # The run already stopped: whatever the bookkeeping above did, the next interrupt must stay answerable.
        arm_interrupt_timeout(
            chat_id,
            resume_params,
            approval_timeout=next_approval_timeout,
            clarification_pending=clarification_pending,
            directory_pending=directory_pending,
            awaiting_answer=collector.has_pending_hitl_replay(),
        )
    logger.info("HITL timeout auto-resume completed: kind=%s, chat_id=%s", kind, chat_id)
