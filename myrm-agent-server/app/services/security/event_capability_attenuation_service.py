"""
[POS] app/services/security/event_capability_attenuation_service.py
[INPUT] myrm_agent_harness.core.security.event_capability_attenuation, app.schemas.event_capability_attenuation
[OUTPUT] EventCapabilityAttenuationService, get_event_capability_attenuation_service

Thread-safe service managing external event signature authentication,
runtime capability attenuation, and multi-channel asynchronous approval tickets.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

import threading
from typing import Optional

from myrm_agent_harness.core.security.event_capability_attenuation import (
    ApprovalTicket as HarnessTicket,
)
from myrm_agent_harness.core.security.event_capability_attenuation import (
    ChannelNotificationTarget as HarnessChannel,
)
from myrm_agent_harness.core.security.event_capability_attenuation import (
    EventCapabilityAttenuationFacade,
)
from myrm_agent_harness.core.security.event_capability_attenuation import (
    EventTrustScopeEnum as HarnessScope,
)
from myrm_agent_harness.core.security.event_capability_attenuation import (
    TicketRiskLevelEnum as HarnessRisk,
)

from app.schemas.event_capability_attenuation import (
    ApprovalTicketResponse,
    ApprovalTicketStatusEnum,
    ApproveTicketRequest,
    ApproveTicketResponse,
    CapabilityAttenuationMetricsResponse,
    ChannelNotificationTargetSchema,
    ConsumeTokenRequest,
    ConsumeTokenResponse,
    CreateTicketRequest,
    EventIngestRequest,
    EventIngestResponse,
    EventTrustScopeEnum,
    RegisterSecretRequest,
    RejectTicketRequest,
    SessionScopeResponse,
    SessionScopeUpdateRequest,
    TicketRiskLevelEnum,
    ToolEvaluationRequest,
    ToolEvaluationResponse,
)


class EventCapabilityAttenuationService:
    """Service wrapping event capability attenuation and asynchronous approval bridge."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._facade = EventCapabilityAttenuationFacade()

    def register_secret(self, req: RegisterSecretRequest) -> bool:
        """Register shared secret key for an external event publisher."""
        with self._lock:
            self._facade.register_event_secret(req.source_name, req.secret_key)
        return True

    def ingest_event(self, req: EventIngestRequest) -> EventIngestResponse:
        """Ingest external event, verify signature, and optionally bind session scope."""
        raw_bytes = req.raw_payload_text.encode("utf-8")
        with self._lock:
            desc = self._facade.verify_and_ingest_event(
                event_id=req.event_id,
                source_name=req.source_name,
                event_type=req.event_type,
                timestamp=req.timestamp,
                raw_payload_bytes=raw_bytes,
                signature=req.signature,
                auto_bind_session_id=req.auto_bind_session_id,
            )
            bound_scope: EventTrustScopeEnum | None = None
            if req.auto_bind_session_id is not None:
                scope = self._facade.get_session_scope(req.auto_bind_session_id)
                bound_scope = EventTrustScopeEnum(scope.value)

        return EventIngestResponse(
            event_id=desc.event_id,
            source_name=desc.source_name,
            is_verified=desc.is_verified,
            bound_scope=bound_scope,
        )

    def evaluate_tool(self, req: ToolEvaluationRequest) -> ToolEvaluationResponse:
        """Evaluate if tool can run directly or requires out-of-band approval."""
        with self._lock:
            is_allowed, reason, risk = self._facade.evaluate_tool(req.session_id, req.tool_name)
            scope = self._facade.get_session_scope(req.session_id)

        return ToolEvaluationResponse(
            is_allowed=is_allowed,
            reason=reason,
            risk_level=TicketRiskLevelEnum(risk.value),
            active_scope=EventTrustScopeEnum(scope.value),
        )

    def set_session_scope(
        self, session_id: str, req: SessionScopeUpdateRequest
    ) -> SessionScopeResponse:
        """Explicitly configure a session's trust scope."""
        harness_scope = HarnessScope(req.scope.value)
        with self._lock:
            self._facade.set_session_scope(session_id, harness_scope)
        return SessionScopeResponse(session_id=session_id, active_scope=req.scope)

    def get_session_scope(self, session_id: str) -> SessionScopeResponse:
        """Inspect a session's active trust scope."""
        with self._lock:
            scope = self._facade.get_session_scope(session_id)
        return SessionScopeResponse(
            session_id=session_id, active_scope=EventTrustScopeEnum(scope.value)
        )

    def create_ticket(self, req: CreateTicketRequest) -> ApprovalTicketResponse:
        """Create an asynchronous approval ticket for attenuated agent action."""
        channels = [
            HarnessChannel(
                channel_type=c.channel_type,
                target_id=c.target_id,
                recipient_name=c.recipient_name,
            )
            for c in req.channels
        ]
        with self._lock:
            ticket = self._facade.create_approval_ticket(
                session_id=req.session_id,
                requested_tool=req.requested_tool,
                risk_level=HarnessRisk(req.risk_level.value),
                action_description=req.action_description,
                diff_payload=req.diff_payload,
                channels=channels,
                custom_ttl_seconds=req.ttl_seconds,
            )
        return self._to_ticket_response(ticket)

    def get_ticket(self, ticket_id: str) -> ApprovalTicketResponse | None:
        """Get ticket by ID."""
        with self._lock:
            ticket = self._facade.get_ticket(ticket_id)
        if ticket is None:
            return None
        return self._to_ticket_response(ticket)

    def list_pending_tickets(self) -> list[ApprovalTicketResponse]:
        """List active pending tickets."""
        with self._lock:
            tickets = self._facade.list_pending_tickets()
        return [self._to_ticket_response(t) for t in tickets]

    def approve_ticket(
        self, ticket_id: str, req: ApproveTicketRequest
    ) -> ApproveTicketResponse | None:
        """Approve a ticket and grant single-use token."""
        with self._lock:
            ticket, token = self._facade.approve_ticket(
                ticket_id=ticket_id,
                decided_by=req.decided_by,
                decision_reason=req.decision_reason,
            )
        if ticket is None or token is None:
            return None
        return ApproveTicketResponse(
            ticket=self._to_ticket_response(ticket),
            execution_token=token,
        )

    def reject_ticket(
        self, ticket_id: str, req: RejectTicketRequest
    ) -> ApprovalTicketResponse | None:
        """Reject a pending ticket."""
        with self._lock:
            ticket = self._facade.reject_ticket(
                ticket_id=ticket_id,
                decided_by=req.decided_by,
                decision_reason=req.decision_reason,
            )
        if ticket is None:
            return None
        return self._to_ticket_response(ticket)

    def consume_token(self, req: ConsumeTokenRequest) -> ConsumeTokenResponse:
        """Consume single-use execution authorization token."""
        with self._lock:
            matched = self._facade.verify_and_consume_token(req.token)
        return ConsumeTokenResponse(
            is_valid=matched is not None,
            matched_ticket_id=matched,
        )

    def get_metrics(self) -> CapabilityAttenuationMetricsResponse:
        """Get operational metrics."""
        with self._lock:
            m = self._facade.get_metrics()
        return CapabilityAttenuationMetricsResponse(
            total_events_received=m.total_events_received,
            verified_events_count=m.verified_events_count,
            rejected_signature_events=m.rejected_signature_events,
            attenuated_executions_count=m.attenuated_executions_count,
            tickets_created=m.tickets_created,
            tickets_approved=m.tickets_approved,
            tickets_rejected=m.tickets_rejected,
            tickets_expired=m.tickets_expired,
        )

    @staticmethod
    def _to_ticket_response(t: HarnessTicket) -> ApprovalTicketResponse:
        channels = [
            ChannelNotificationTargetSchema(
                channel_type=c.channel_type,
                target_id=c.target_id,
                recipient_name=c.recipient_name,
            )
            for c in t.notification_channels
        ]
        return ApprovalTicketResponse(
            ticket_id=t.ticket_id,
            session_id=t.session_id,
            requested_tool=t.requested_tool,
            risk_level=TicketRiskLevelEnum(t.risk_level.value),
            action_description=t.action_description,
            diff_payload=t.diff_payload,
            created_at=t.created_at,
            expires_at=t.expires_at,
            status=ApprovalTicketStatusEnum(t.status.value),
            decided_by=t.decided_by,
            decision_reason=t.decision_reason,
            notification_channels=channels,
        )


_SERVICE_INSTANCE: Optional[EventCapabilityAttenuationService] = None
_SERVICE_LOCK = threading.Lock()


def get_event_capability_attenuation_service() -> EventCapabilityAttenuationService:
    """Get singleton instance of EventCapabilityAttenuationService."""
    global _SERVICE_INSTANCE
    with _SERVICE_LOCK:
        if _SERVICE_INSTANCE is None:
            _SERVICE_INSTANCE = EventCapabilityAttenuationService()
        return _SERVICE_INSTANCE
