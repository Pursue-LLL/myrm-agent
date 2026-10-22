"""Service mediating Zero-Token Fleet Runtime Event Mirror Contract (Item 48).

[INPUT]
- MirrorEventRequest, BatchMirrorEventRequest, LlmCallCheckRequest, SimulateViolationRequest.

[OUTPUT]
- ZeroTokenContractService managing zero-token guards, event projection, and Doctor audit reports.

[POS]
- Server-side service layer for Zero-Token Contract.
"""

from __future__ import annotations

import logging
import threading
from datetime import UTC, datetime

from myrm_agent_harness.agent.sub_agents.zero_token_contract import (
    VizCallAuditRecord,
    ZeroTokenAuditSnapshot,
    ZeroTokenContractGuard,
    ZeroTokenContractViolationError,
    ZeroTokenEvent,
)

from app.schemas.zero_token_contract import (
    BatchMirrorEventRequest,
    LlmCallCheckRequest,
    LlmCallCheckResponse,
    MirrorEventRequest,
    SimulateViolationRequest,
    VizCallAuditRecordDTO,
    ZeroTokenAuditReportResponse,
)

logger = logging.getLogger(__name__)


def _record_to_dto(rec: VizCallAuditRecord) -> VizCallAuditRecordDTO:
    iso_time = datetime.fromtimestamp(rec.timestamp, tz=UTC).isoformat()
    return VizCallAuditRecordDTO(
        caller_surface=rec.caller_surface,
        prompt_chars=rec.prompt_chars,
        is_violation=rec.is_violation,
        intercepted_reason=rec.intercepted_reason,
        timestamp=iso_time,
    )


def _snapshot_to_dto(snap: ZeroTokenAuditSnapshot) -> ZeroTokenAuditReportResponse:
    last_mirrored_iso = (
        datetime.fromtimestamp(snap.last_mirrored_at, tz=UTC).isoformat()
        if snap.last_mirrored_at is not None
        else None
    )
    return ZeroTokenAuditReportResponse(
        chat_id=snap.chat_id,
        total_events_mirrored=snap.total_events_mirrored,
        total_tokens_spent=snap.total_tokens_spent,
        saved_tokens_estimated=snap.saved_tokens_estimated,
        violations_intercepted=snap.violations_intercepted,
        is_compliant=snap.is_compliant,
        recent_violations=[_record_to_dto(r) for r in snap.recent_violations],
        last_mirrored_at=last_mirrored_iso,
    )


class ZeroTokenContractService:
    """Thread-safe session-scoped service managing Zero-Token Contract Guards."""

    def __init__(self, estimated_tokens_per_event: int = 150) -> None:
        self._estimated_tokens_per_event = estimated_tokens_per_event
        self._lock = threading.Lock()
        self._guards: dict[str, ZeroTokenContractGuard] = {}

    def get_or_create_guard(self, chat_id: str) -> ZeroTokenContractGuard:
        """Retrieves or creates a session-scoped ZeroTokenContractGuard."""
        with self._lock:
            if chat_id not in self._guards:
                self._guards[chat_id] = ZeroTokenContractGuard(
                    chat_id=chat_id,
                    estimated_tokens_per_event=self._estimated_tokens_per_event,
                )
            return self._guards[chat_id]

    def mirror_event(
        self, chat_id: str, request: MirrorEventRequest
    ) -> ZeroTokenAuditReportResponse:
        """Mirrors a single runtime event to the visualization layer."""
        guard = self.get_or_create_guard(chat_id)
        event = ZeroTokenEvent(
            event_id=request.event_id,
            source=request.source.value,
            event_type=request.event_type.value,
            agent_id=request.agent_id,
            payload=request.payload,
        )
        snapshot = guard.mirror_runtime_event(event)
        logger.debug(
            "Mirrored zero-token event %s for chat %s (Total mirrored: %d)",
            request.event_id,
            chat_id,
            snapshot.total_events_mirrored,
        )
        return _snapshot_to_dto(snapshot)

    def mirror_batch_events(
        self, chat_id: str, request: BatchMirrorEventRequest
    ) -> ZeroTokenAuditReportResponse:
        """Mirrors multiple runtime events atomically to visualization layer."""
        guard = self.get_or_create_guard(chat_id)
        events = [
            ZeroTokenEvent(
                event_id=req.event_id,
                source=req.source.value,
                event_type=req.event_type.value,
                agent_id=req.agent_id,
                payload=req.payload,
            )
            for req in request.events
        ]
        snapshot = guard.mirror_batch_events(events)
        return _snapshot_to_dto(snapshot)

    def check_or_intercept_llm_call(
        self, chat_id: str, request: LlmCallCheckRequest
    ) -> LlmCallCheckResponse:
        """Doctor inspection: blocks illegal LLM calls from viz surfaces."""
        guard = self.get_or_create_guard(chat_id)
        try:
            guard.intercept_llm_call(
                caller_surface=request.caller_surface,
                prompt=request.prompt,
            )
            return LlmCallCheckResponse(
                allowed=True,
                intercepted=False,
                reason=None,
            )
        except ZeroTokenContractViolationError as exc:
            logger.warning(
                "Zero-Token violation blocked for chat %s: %s",
                chat_id,
                exc.reason,
            )
            return LlmCallCheckResponse(
                allowed=False,
                intercepted=True,
                reason=exc.reason,
            )

    def simulate_violation(
        self, chat_id: str, request: SimulateViolationRequest
    ) -> tuple[LlmCallCheckResponse, ZeroTokenAuditReportResponse]:
        """Triggers a simulated contract violation to exercise Doctor interception."""
        check_resp = self.check_or_intercept_llm_call(
            chat_id=chat_id,
            request=LlmCallCheckRequest(
                caller_surface=request.caller_surface,
                prompt=request.test_prompt,
            ),
        )
        audit_report = self.get_audit_report(chat_id)
        return check_resp, audit_report

    def get_audit_report(self, chat_id: str) -> ZeroTokenAuditReportResponse:
        """Returns the current Zero-Token audit snapshot for the chat session."""
        guard = self.get_or_create_guard(chat_id)
        return _snapshot_to_dto(guard.get_audit_snapshot())

    def reset_session(self, chat_id: str) -> ZeroTokenAuditReportResponse:
        """Resets the audit ledger for the chat session."""
        guard = self.get_or_create_guard(chat_id)
        guard.reset()
        return _snapshot_to_dto(guard.get_audit_snapshot())


# Global singleton instance for server routing
zero_token_contract_service = ZeroTokenContractService()
