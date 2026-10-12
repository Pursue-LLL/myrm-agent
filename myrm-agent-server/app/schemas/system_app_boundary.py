"""
[POS] app/schemas/system_app_boundary.py
[INPUT] pydantic
[OUTPUT] System app privacy boundary request/response DTOs, consent DTOs, audit and metrics schemas
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class AppAccessRequestDTO(BaseModel):
    """Payload to request interaction with a local system-level application."""

    request_id: str = Field(..., description="Unique access request identifier")
    session_id: str = Field(..., description="Active conversational session ID")
    app_type: str = Field(
        ...,
        description="Target app type: MAIL, NOTES, PHOTOS, CALENDAR, CONTACTS, REMINDERS, OTHER",
    )
    operation_type: str = Field(
        ...,
        description="Operation nature: READ_ONLY, MUTATE_WRITE, DELETE_PURGE",
    )
    target_container: str = Field(
        ...,
        description="Target resource folder, label, calendar name, or album name",
    )
    payload_summary: str = Field(
        ...,
        description="Summary of data being read, written, or manipulated",
    )
    is_external_tainted: bool = Field(
        default=False,
        description="Whether the active context was derived from untrusted external content",
    )


class AppAccessVerdictResponseDTO(BaseModel):
    """Verdict rendered by the privacy boundary gate."""

    request_id: str = Field(..., description="Request identifier")
    decision: str = Field(
        ...,
        description="Decision: PERMITTED_SILENT, REQUIRE_WRITE_CONSENT, BOUNDARY_VIOLATION_BLOCKED, EMERGENCY_APP_LOCKED",
    )
    is_allowed: bool = Field(..., description="Whether action is immediately allowed")
    diagnostic_reason: str = Field(..., description="Audit explanation")
    audit_id: str = Field(..., description="Audit record reference identifier")


class GrantWriteConsentRequestDTO(BaseModel):
    """Payload for human user to grant one-time execution consent."""

    request_id: str = Field(..., description="Pending request identifier")
    approver_note: str = Field(
        default="Authorized by User",
        description="Explanatory user confirmation note",
    )


class RejectWriteConsentRequestDTO(BaseModel):
    """Payload for human user to reject a held write request."""

    request_id: str = Field(..., description="Pending request identifier")
    reason: str = Field(
        default="Rejected by User",
        description="Reason recorded for rejection",
    )


class SetScopeRuleRequestDTO(BaseModel):
    """Payload to declare or update scoping rules for a system application."""

    app_type: str = Field(..., description="Target system application name")
    allowed_containers: list[str] = Field(
        default_factory=list,
        description="Whitelisted folders/labels (empty permits any container within app)",
    )
    allow_mutations_without_prompt: bool = Field(
        default=False,
        description="Whether mutations within whitelisted containers can bypass consent prompt",
    )
    is_locked_down: bool = Field(
        default=False,
        description="Whether application is completely locked down",
    )


class SystemAppScopeRuleResponseDTO(BaseModel):
    """Details of declared boundary rules for a system application."""

    app_type: str = Field(..., description="System application name")
    allowed_containers: list[str] = Field(..., description="Whitelisted container names")
    allow_mutations_without_prompt: bool = Field(..., description="Unprompted mutation policy")
    is_locked_down: bool = Field(..., description="Emergency lockdown posture")


class SystemAppAuditRecordResponseDTO(BaseModel):
    """Audit log entry capturing local system app access attempt."""

    audit_id: str = Field(..., description="Unique audit event ID")
    timestamp_epoch: float = Field(..., description="Event epoch timestamp")
    request_id: str = Field(..., description="Request identifier")
    session_id: str = Field(..., description="Session identifier")
    app_type: str = Field(..., description="Application accessed")
    operation_type: str = Field(..., description="Operation performed")
    target_container: str = Field(..., description="Target container")
    is_allowed: bool = Field(..., description="Whether operation was permitted")
    reason: str = Field(..., description="Verdict rationale")


class SystemAppBoundaryMetricsResponseDTO(BaseModel):
    """Cumulative telemetry metrics for local system app boundary access."""

    requests_evaluated_total: int = Field(..., description="Total access requests evaluated")
    silent_reads_permitted_total: int = Field(..., description="Total read-only actions permitted silently")
    write_consents_requested_total: int = Field(..., description="Total write operations held for consent")
    write_consents_granted_total: int = Field(..., description="Total write consents granted by user")
    boundary_violations_blocked_total: int = Field(..., description="Total out-of-boundary requests blocked")
    lockdown_blocked_total: int = Field(..., description="Total requests blocked due to emergency lockdown")
