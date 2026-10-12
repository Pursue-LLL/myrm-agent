"""
[POS] app/schemas/outbound_ebrake_mesh.py
[INPUT] pydantic
[OUTPUT] OutboundAction DTOs, GhostInspection DTOs, EBrake DTOs, CalendarMesh DTOs, Metrics DTOs

Pydantic schemas for Outbound Irreversible Action E-Brake & Privacy-Preserving Chief of Staff Mesh Suite.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class InspectOutboundActionRequestDTO(BaseModel):
    """Payload to perform pre-flight ghost inspection on an outbound side effect."""

    action_type: str = Field(
        ...,
        description="Type of action: EMAIL_DISPATCH, IM_BROADCAST, WEBHOOK_CALL, CALENDAR_MUTATION, SOCIAL_POST",
    )
    destination_target: str = Field(
        ...,
        description="Target destination host, recipient email, or webhook URL",
    )
    payload_text: str = Field(
        ...,
        description="Full textual content or serializable body of outbound action",
    )


class GhostInspectionVerdictResponseDTO(BaseModel):
    """Result of pre-flight shadow inspection."""

    is_safe_to_queue: bool = Field(
        ..., description="Whether action satisfies boundary and token exfiltration checks"
    )
    risk_tier: str = Field(
        ...,
        description="Audience risk tier: INTERNAL_SAFE, EXTERNAL_TRUSTED, EXTERNAL_UNTRUSTED, PROHIBITED_LEAK",
    )
    tainted_tokens_detected: list[str] = Field(
        default_factory=list,
        description="Detected credentials, private keys, or high-risk tokens",
    )
    ghost_summary: str = Field(..., description="Shadow execution preview summary")
    diagnostic_reason: str = Field(..., description="Diagnostic justification for inspection verdict")


class EnqueueOutboundActionRequestDTO(BaseModel):
    """Payload to buffer an inspected outbound action with a grace cooldown."""

    task_id: str = Field(..., description="Associated autonomous task or session ID")
    action_type: str = Field(
        ...,
        description="Type of action: EMAIL_DISPATCH, IM_BROADCAST, WEBHOOK_CALL, CALENDAR_MUTATION, SOCIAL_POST",
    )
    destination_target: str = Field(..., description="Target destination host, email, or URL")
    payload_text: str = Field(..., description="Full payload to dispatch after cooldown")
    grace_period_seconds: float = Field(
        default=10.0,
        ge=5.0,
        le=60.0,
        description="Cooldown duration before irreversible delivery",
    )


class OutboundActionItemResponseDTO(BaseModel):
    """Buffered outbound action item snapshot."""

    action_id: str = Field(..., description="Unique action identifier")
    task_id: str = Field(..., description="Task ID")
    action_type: str = Field(..., description="Action type")
    destination_target: str = Field(..., description="Destination target")
    payload_summary: str = Field(..., description="Preview summary")
    risk_tier: str = Field(..., description="Risk tier")
    enqueued_at_epoch: float = Field(..., description="Enqueue epoch timestamp")
    grace_period_seconds: float = Field(..., description="Cooldown length in seconds")
    status: str = Field(
        ...,
        description="Status: QUEUED_IN_GRACE_PERIOD, DISPATCHED_AFTER_GRACE, CANCELLED_BY_USER, ABORTED_BY_E_BRAKE",
    )
    cancellation_reason: str | None = Field(
        default=None, description="Reason if cancelled or aborted"
    )


class CancelOutboundActionRequestDTO(BaseModel):
    """Payload to cancel an action during its cooldown."""

    reason: str = Field(
        default="User manual cancellation via UI",
        description="Human operator cancellation justification",
    )


class TriggerEBrakeRequestDTO(BaseModel):
    """Payload to trigger global emergency physical brake."""

    reason: str = Field(
        default="Physical emergency STOP triggered by operator",
        description="Emergency justification for immediate abort",
    )


class EBrakeStatusResponseDTO(BaseModel):
    """Status snapshot of global emergency brake."""

    is_e_brake_active: bool = Field(..., description="Whether emergency stop is latched")
    last_triggered_at_epoch: float | None = Field(
        default=None, description="Timestamp of most recent e-brake trigger"
    )
    trigger_reason: str | None = Field(
        default=None, description="Reason given during e-brake activation"
    )
    actions_aborted_count: int = Field(
        ..., description="Cumulative total of actions aborted by e-brake"
    )


class CalendarTimeSlotDTO(BaseModel):
    """Zero-knowledge free/busy slot for A2A negotiation."""

    slot_index: int = Field(..., description="Discrete index representing time segment")
    start_time_iso: str = Field(..., description="ISO 8601 UTC timestamp")
    duration_minutes: int = Field(default=30, description="Slot duration in minutes")
    is_free: bool = Field(..., description="Whether slot is free from conflicts")
    preference_score: float = Field(
        default=1.0,
        ge=0.0,
        description="Subjective preference score (0.0 to 1.0 individual, up to 2.0 joint)",
    )


class NegotiateCalendarRequestDTO(BaseModel):
    """Payload to conduct privacy-preserving A2A calendar coordination."""

    party_a_id: str = Field(..., description="Identifier for party A chief of staff")
    party_b_id: str = Field(..., description="Identifier for party B chief of staff")
    party_a_slots: list[CalendarTimeSlotDTO] = Field(
        ..., description="Free/busy bitmask slots for party A"
    )
    party_b_slots: list[CalendarTimeSlotDTO] = Field(
        ..., description="Free/busy bitmask slots for party B"
    )


class CalendarNegotiationResponseDTO(BaseModel):
    """Result of A2A zero-knowledge calendar negotiation."""

    negotiation_id: str = Field(..., description="Unique negotiation session ID")
    party_a_id: str = Field(..., description="Party A identifier")
    party_b_id: str = Field(..., description="Party B identifier")
    matched_slots: list[CalendarTimeSlotDTO] = Field(
        ..., description="All mutually free time slots"
    )
    optimal_slot: CalendarTimeSlotDTO | None = Field(
        default=None, description="Top-ranked joint optimal slot"
    )
    privacy_preserved: bool = Field(..., description="Confirmation of zero privacy disclosure")
    diagnostic_notes: str = Field(..., description="Diagnostic negotiation logs")


class OutboundEBrakeMetricsResponseDTO(BaseModel):
    """Cumulative operational metrics for outbound guard, e-brake, and calendar mesh."""

    inspections_total: int = Field(..., description="Total outbound inspections")
    blocked_by_ghost_gate_total: int = Field(..., description="Total actions blocked by ghost gate")
    queued_in_grace_period_total: int = Field(..., description="Total actions queued in grace period")
    dispatched_total: int = Field(..., description="Total actions successfully dispatched")
    cancelled_by_user_total: int = Field(..., description="Total actions cancelled by user")
    e_brake_activations_total: int = Field(..., description="Total emergency brake triggers")
    calendar_negotiations_total: int = Field(..., description="Total calendar negotiations executed")
