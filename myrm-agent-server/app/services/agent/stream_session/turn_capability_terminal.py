"""
[INPUT]
- app.services.agent.params.models::AgentRequest (POS: agent-stream request contract)
- app.database.models::TurnCapabilityMetricEvent (POS: turn capability telemetry ORM)
- app.services.agent.stream_session.stream_session_types::AgentStreamSession (POS: carries the once-only terminal recorded flag of the turn)
- myrm_agent_harness.toolkits.llms.transport::LLMCallError (POS: model-call failure base, carries the HTTP status)

[OUTPUT]
- has_turn_capability_terminal_context: gate terminal telemetry writes by request payload.
- record_turn_capability_send_completed: persist authoritative send_completed terminal event.
- record_turn_capability_send_failed: persist authoritative send_failed terminal event.
- record_turn_capability_failed_once: record send_failed for a session unless its terminal state is already recorded.
- record_turn_capability_completed_once: record send_completed for a session unless its terminal state is already recorded.
- classify_turn_capability_failure_reason: map runtime exceptions to failure_reason enum.

[POS]
Server-authoritative terminal telemetry anchor for one-turn Skill/MCP capability overrides.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Literal

import httpx
from myrm_agent_harness.toolkits.llms.transport import LLMCallError

from app.database.models import TurnCapabilityMetricEvent
from app.platform_utils import get_session_factory
from app.services.agent.params.models import AgentRequest, TurnCapabilityTelemetryRequest

if TYPE_CHECKING:
    from app.services.agent.stream_session.stream_session_types import AgentStreamSession

TurnCapabilityFailureReason = Literal[
    "network_error",
    "archive_restore_invalid",
    "abort",
    "server_error",
    "risk_held",
    "unknown_error",
]

logger = logging.getLogger(__name__)


def has_turn_capability_terminal_context(request: AgentRequest) -> bool:
    telemetry = getattr(request, "turn_capability_telemetry", None)
    return isinstance(telemetry, TurnCapabilityTelemetryRequest)


def _resolve_turn_capability_context_key(request: AgentRequest) -> str:
    chat_id = (request.chat_id or "").strip()
    if chat_id:
        return f"chat:{chat_id}"
    return "chat:unknown"


_TIMEOUT_STATUSES = frozenset({408, 504})


def classify_turn_capability_failure_reason(error: BaseException) -> TurnCapabilityFailureReason:
    if isinstance(error, asyncio.CancelledError):
        return "abort"

    # A model-call failure states what happened: the provider's HTTP status, or a connection that broke. Its class
    # name ("LLMHTTPError") and message prefix say nothing about the cause, so wording is read only from errors that
    # carry no such fact. Statuses below 500 are the caller's or the account's problem, not a server fault.
    if isinstance(error, LLMCallError) and error.status_code is not None:
        if error.status_code in _TIMEOUT_STATUSES:
            return "network_error"
        return "server_error" if error.status_code >= 500 else "unknown_error"
    if isinstance(error, httpx.TransportError):
        return "network_error"

    error_name = type(error).__name__.lower()
    error_message = str(error).lower()
    combined = f"{error_name} {error_message}"

    if "archive" in combined and "restore" in combined and "invalid" in combined:
        return "archive_restore_invalid"
    if "abort" in combined or "cancel" in combined:
        return "abort"
    if "network" in combined or "fetch" in combined or "connection" in combined or "timeout" in combined:
        return "network_error"
    if "server" in combined or "status" in combined or "http" in combined:
        return "server_error"

    return "unknown_error"


async def _write_turn_capability_event(
    *,
    source: Literal["direct", "queue_drain"],
    event_type: Literal["send_completed", "send_failed"],
    context_key: str,
    effective_skill_count: int | None = None,
    effective_mcp_count: int | None = None,
    failure_reason: TurnCapabilityFailureReason | None = None,
) -> bool:
    session_factory = get_session_factory()
    db = session_factory()
    try:
        async with db:
            event = TurnCapabilityMetricEvent(
                source=source,
                event_type=event_type,
                context_key=context_key,
                effective_skill_count=effective_skill_count,
                effective_mcp_count=effective_mcp_count,
                failure_reason=failure_reason,
            )
            db.add(event)
            await db.commit()
        return True
    except Exception:
        try:
            await db.rollback()
        except Exception:
            logger.debug(
                "turn_capability_terminal: rollback skipped for %s event",
                event_type,
            )
        logger.exception("turn_capability_terminal: failed to persist %s event", event_type)
        return False


async def record_turn_capability_send_completed(request: AgentRequest) -> bool:
    telemetry = getattr(request, "turn_capability_telemetry", None)
    if not isinstance(telemetry, TurnCapabilityTelemetryRequest):
        return False
    return await _write_turn_capability_event(
        source=telemetry.source,
        event_type="send_completed",
        context_key=_resolve_turn_capability_context_key(request),
        effective_skill_count=telemetry.effective_skill_count,
        effective_mcp_count=telemetry.effective_mcp_count,
    )


async def record_turn_capability_send_failed(
    request: AgentRequest,
    reason: TurnCapabilityFailureReason,
) -> bool:
    telemetry = getattr(request, "turn_capability_telemetry", None)
    if not isinstance(telemetry, TurnCapabilityTelemetryRequest):
        return False
    return await _write_turn_capability_event(
        source=telemetry.source,
        event_type="send_failed",
        context_key=_resolve_turn_capability_context_key(request),
        failure_reason=reason,
    )


async def record_turn_capability_failed_once(
    session: AgentStreamSession,
    reason: TurnCapabilityFailureReason,
) -> None:
    if session.turn_capability_terminal_recorded or not has_turn_capability_terminal_context(session.request):
        return
    recorded = await record_turn_capability_send_failed(
        session.request,
        reason,
    )
    if recorded:
        session.turn_capability_terminal_recorded = True


async def record_turn_capability_completed_once(
    session: AgentStreamSession,
) -> None:
    if session.turn_capability_terminal_recorded or not has_turn_capability_terminal_context(session.request):
        return
    recorded = await record_turn_capability_send_completed(session.request)
    if recorded:
        session.turn_capability_terminal_recorded = True
