"""
[POS] app/services/security/outbound_ebrake_mesh_service.py
[INPUT] app.schemas.outbound_ebrake_mesh, myrm_agent_harness.core.security.outbound_ebrake_mesh
[OUTPUT] OutboundEBrakeMeshService, get_outbound_ebrake_mesh_service

Service layer for Outbound Irreversible Action E-Brake & Privacy-Preserving Chief of Staff Mesh Suite.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

import logging

from myrm_agent_harness.core.security.outbound_ebrake_mesh import (
    CalendarTimeSlot,
    GhostInspectionVerdict,
    OutboundActionItem,
    OutboundActionType,
    OutboundEBrakeAndChiefOfStaffMeshFacade,
)

from app.schemas.outbound_ebrake_mesh import (
    CalendarNegotiationResponseDTO,
    CalendarTimeSlotDTO,
    CancelOutboundActionRequestDTO,
    EBrakeStatusResponseDTO,
    EnqueueOutboundActionRequestDTO,
    GhostInspectionVerdictResponseDTO,
    InspectOutboundActionRequestDTO,
    NegotiateCalendarRequestDTO,
    OutboundActionItemResponseDTO,
    OutboundEBrakeMetricsResponseDTO,
    TriggerEBrakeRequestDTO,
)

logger = logging.getLogger(__name__)


class OutboundEBrakeMeshService:
    """Orchestrates outbound side-effect shadow inspection, grace-period buffering, and physical stop."""

    def __init__(
        self, facade: OutboundEBrakeAndChiefOfStaffMeshFacade | None = None
    ) -> None:
        self._facade = facade or OutboundEBrakeAndChiefOfStaffMeshFacade()

    def inspect_outbound_action(
        self, request: InspectOutboundActionRequestDTO
    ) -> GhostInspectionVerdictResponseDTO:
        """Perform pre-flight ghost inspection on outbound side effect."""
        action_type = self._parse_action_type(request.action_type)
        verdict: GhostInspectionVerdict = self._facade.inspect_outbound_action(
            action_type=action_type,
            destination_target=request.destination_target,
            payload_text=request.payload_text,
        )
        return GhostInspectionVerdictResponseDTO(
            is_safe_to_queue=verdict.is_safe_to_queue,
            risk_tier=verdict.risk_tier.value,
            tainted_tokens_detected=list(verdict.tainted_tokens_detected),
            ghost_summary=verdict.ghost_summary,
            diagnostic_reason=verdict.diagnostic_reason,
        )

    def enqueue_action(
        self, request: EnqueueOutboundActionRequestDTO
    ) -> OutboundActionItemResponseDTO:
        """Inspect and enqueue an outbound action into grace cooldown buffer."""
        action_type = self._parse_action_type(request.action_type)
        verdict = self._facade.inspect_outbound_action(
            action_type=action_type,
            destination_target=request.destination_target,
            payload_text=request.payload_text,
        )
        item = self._facade.enqueue_action(
            task_id=request.task_id,
            action_type=action_type,
            destination_target=request.destination_target,
            payload_text=request.payload_text,
            risk_tier=verdict.risk_tier,
            grace_period_seconds=request.grace_period_seconds,
        )
        return self._map_action_item(item)

    def cancel_action(
        self, action_id: str, request: CancelOutboundActionRequestDTO
    ) -> bool:
        """Cancel a pending action during cooldown countdown."""
        return self._facade.cancel_action(action_id=action_id, reason=request.reason)

    def flush_action(self, action_id: str) -> bool:
        """Bypass cooldown and immediately dispatch action."""
        return self._facade.flush_action(action_id=action_id)

    def poll_and_dispatch(self) -> list[OutboundActionItemResponseDTO]:
        """Poll and transition expired items into dispatched state."""
        dispatched = self._facade.poll_and_dispatch()
        return [self._map_action_item(it) for it in dispatched]

    def trigger_e_brake(self, request: TriggerEBrakeRequestDTO) -> int:
        """Instantly abort all pending outbound dispatches and latch e-brake."""
        return self._facade.trigger_e_brake(reason=request.reason)

    def reset_e_brake(self) -> bool:
        """Reset emergency brake."""
        return self._facade.reset_e_brake()

    def get_e_brake_status(self) -> EBrakeStatusResponseDTO:
        """Get emergency brake status snapshot."""
        st = self._facade.get_e_brake_status()
        return EBrakeStatusResponseDTO(
            is_e_brake_active=st.is_e_brake_active,
            last_triggered_at_epoch=st.last_triggered_at_epoch,
            trigger_reason=st.trigger_reason,
            actions_aborted_count=st.actions_aborted_count,
        )

    def get_action(self, action_id: str) -> OutboundActionItemResponseDTO | None:
        """Lookup action item by ID."""
        item = self._facade.get_action(action_id=action_id)
        if item is None:
            return None
        return self._map_action_item(item)

    def list_queued_actions(self) -> list[OutboundActionItemResponseDTO]:
        """List currently pending actions waiting in cooldown buffer."""
        queued = self._facade.list_queued_actions()
        return [self._map_action_item(it) for it in queued]

    def negotiate_calendar(
        self, request: NegotiateCalendarRequestDTO
    ) -> CalendarNegotiationResponseDTO:
        """Execute privacy-preserving A2A calendar negotiation."""
        slots_a = tuple(
            CalendarTimeSlot(
                slot_index=s.slot_index,
                start_time_iso=s.start_time_iso,
                duration_minutes=s.duration_minutes,
                is_free=s.is_free,
                preference_score=s.preference_score,
            )
            for s in request.party_a_slots
        )
        slots_b = tuple(
            CalendarTimeSlot(
                slot_index=s.slot_index,
                start_time_iso=s.start_time_iso,
                duration_minutes=s.duration_minutes,
                is_free=s.is_free,
                preference_score=s.preference_score,
            )
            for s in request.party_b_slots
        )
        res = self._facade.negotiate_calendar(
            party_a_id=request.party_a_id,
            party_b_id=request.party_b_id,
            party_a_slots=slots_a,
            party_b_slots=slots_b,
        )
        matched_dtos = [
            CalendarTimeSlotDTO(
                slot_index=m.slot_index,
                start_time_iso=m.start_time_iso,
                duration_minutes=m.duration_minutes,
                is_free=m.is_free,
                preference_score=m.preference_score,
            )
            for m in res.matched_slots
        ]
        optimal_dto = (
            CalendarTimeSlotDTO(
                slot_index=res.optimal_slot.slot_index,
                start_time_iso=res.optimal_slot.start_time_iso,
                duration_minutes=res.optimal_slot.duration_minutes,
                is_free=res.optimal_slot.is_free,
                preference_score=res.optimal_slot.preference_score,
            )
            if res.optimal_slot is not None
            else None
        )
        return CalendarNegotiationResponseDTO(
            negotiation_id=res.negotiation_id,
            party_a_id=res.party_a_id,
            party_b_id=res.party_b_id,
            matched_slots=matched_dtos,
            optimal_slot=optimal_dto,
            privacy_preserved=res.privacy_preserved,
            diagnostic_notes=res.diagnostic_notes,
        )

    def get_metrics(self) -> OutboundEBrakeMetricsResponseDTO:
        """Get operational metric counters."""
        m = self._facade.metrics
        return OutboundEBrakeMetricsResponseDTO(
            inspections_total=m.inspections_total,
            blocked_by_ghost_gate_total=m.blocked_by_ghost_gate_total,
            queued_in_grace_period_total=m.queued_in_grace_period_total,
            dispatched_total=m.dispatched_total,
            cancelled_by_user_total=m.cancelled_by_user_total,
            e_brake_activations_total=m.e_brake_activations_total,
            calendar_negotiations_total=m.calendar_negotiations_total,
        )

    @staticmethod
    def _parse_action_type(type_str: str) -> OutboundActionType:
        """Parse string to OutboundActionType safely with fallback."""
        normalized = type_str.strip().upper()
        for t in OutboundActionType:
            if t.value == normalized or t.name == normalized:
                return t
        return OutboundActionType.EMAIL_DISPATCH

    @staticmethod
    def _map_action_item(item: OutboundActionItem) -> OutboundActionItemResponseDTO:
        return OutboundActionItemResponseDTO(
            action_id=item.action_id,
            task_id=item.task_id,
            action_type=item.action_type.value,
            destination_target=item.destination_target,
            payload_summary=item.payload_summary,
            risk_tier=item.risk_tier.value,
            enqueued_at_epoch=item.enqueued_at_epoch,
            grace_period_seconds=item.grace_period_seconds,
            status=item.status.value,
            cancellation_reason=item.cancellation_reason,
        )


_service_instance: OutboundEBrakeMeshService | None = None


def get_outbound_ebrake_mesh_service() -> OutboundEBrakeMeshService:
    """Retrieve singleton instance of OutboundEBrakeMeshService."""
    global _service_instance
    if _service_instance is None:
        _service_instance = OutboundEBrakeMeshService()
    return _service_instance
