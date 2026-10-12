"""
[POS] app/schemas/event_capability_attenuation.py
[INPUT] pydantic, enum
[OUTPUT] EventTrustScopeEnum, ApprovalTicketStatusEnum, TicketRiskLevelEnum, ChannelNotificationTargetSchema, RegisterSecretRequest, EventIngestRequest, EventIngestResponse, ToolEvaluationRequest, ToolEvaluationResponse, CreateTicketRequest, ApprovalTicketResponse, ApproveTicketRequest, ApproveTicketResponse, RejectTicketRequest, ConsumeTokenRequest, ConsumeTokenResponse, SessionScopeUpdateRequest, SessionScopeResponse, CapabilityAttenuationMetricsResponse

Pydantic schemas for Event-Triggered Capability Attenuation & Async Approval Bridge Suite.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class EventTrustScopeEnum(StrEnum):
    """Execution context trust scope."""

    USER_INTERACTIVE = "USER_INTERACTIVE"
    LOW_TRUST_EVENT_SCOPE = "LOW_TRUST_EVENT_SCOPE"
    ISOLATED_QUARANTINE = "ISOLATED_QUARANTINE"


class ApprovalTicketStatusEnum(StrEnum):
    """Lifecycle status for unattended approval tickets."""

    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class TicketRiskLevelEnum(StrEnum):
    """Risk severity classification for requested write actions."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ChannelNotificationTargetSchema(BaseModel):
    """Out-of-band communication destination."""

    channel_type: str = Field(..., min_length=1, max_length=64, description="Channel protocol, e.g. feishu, telegram")
    target_id: str = Field(..., min_length=1, max_length=128, description="Chat group or webhook recipient identifier")
    recipient_name: str | None = Field(default=None, description="Human recipient alias")


class RegisterSecretRequest(BaseModel):
    """Payload to register source secret for HMAC event authentication."""

    source_name: str = Field(..., min_length=1, max_length=128, description="Source name identifier")
    secret_key: str = Field(..., min_length=1, description="HMAC shared secret key")


class EventIngestRequest(BaseModel):
    """Payload representing an incoming external event."""

    event_id: str = Field(..., min_length=1, max_length=128, description="Unique event identifier")
    source_name: str = Field(..., min_length=1, max_length=128, description="Registered event source")
    event_type: str = Field(..., min_length=1, max_length=64, description="Type of event, e.g. webhook, push")
    timestamp: float = Field(..., ge=0.0, description="Epoch timestamp of generation")
    raw_payload_text: str = Field(..., description="Raw string body of event payload")
    signature: str | None = Field(default=None, description="HMAC-SHA256 hex signature")
    auto_bind_session_id: str | None = Field(default=None, description="Session ID to automatically bind to low-trust scope")


class EventIngestResponse(BaseModel):
    """Outcome of event verification and scope binding."""

    event_id: str = Field(..., description="Event identifier")
    source_name: str = Field(..., description="Event publisher")
    is_verified: bool = Field(..., description="True if HMAC cryptographic signature verified")
    bound_scope: EventTrustScopeEnum | None = Field(default=None, description="Bound session trust scope if applicable")


class ToolEvaluationRequest(BaseModel):
    """Payload to evaluate tool permission in context."""

    session_id: str = Field(..., min_length=1, description="Agent execution session identifier")
    tool_name: str = Field(..., min_length=1, description="Tool function identifier")


class ToolEvaluationResponse(BaseModel):
    """Result of tool permission check under active scope."""

    is_allowed: bool = Field(..., description="True if tool can run directly")
    reason: str = Field(..., description="Explanation of decision")
    risk_level: TicketRiskLevelEnum = Field(..., description="Calculated action risk level")
    active_scope: EventTrustScopeEnum = Field(..., description="Active session trust scope")


class CreateTicketRequest(BaseModel):
    """Payload to create an asynchronous approval ticket."""

    session_id: str = Field(..., min_length=1, description="Associated session identifier")
    requested_tool: str = Field(..., min_length=1, description="Tool requested by attenuated agent")
    risk_level: TicketRiskLevelEnum = Field(..., description="Risk level")
    action_description: str = Field(..., min_length=1, description="Explanation of why action is required")
    diff_payload: str = Field(..., description="Code or parameter difference payload")
    channels: list[ChannelNotificationTargetSchema] = Field(default_factory=list, description="Target notification channels")
    ttl_seconds: float | None = Field(default=None, ge=1.0, description="Optional custom ticket time-to-live in seconds")


class ApprovalTicketResponse(BaseModel):
    """Asynchronous approval ticket descriptor."""

    ticket_id: str = Field(..., description="Unique ticket identifier")
    session_id: str = Field(..., description="Session identifier")
    requested_tool: str = Field(..., description="Requested tool name")
    risk_level: TicketRiskLevelEnum = Field(..., description="Risk classification")
    action_description: str = Field(..., description="Action narrative")
    diff_payload: str = Field(..., description="Diff payload")
    created_at: float = Field(..., description="Epoch created at")
    expires_at: float = Field(..., description="Epoch expires at")
    status: ApprovalTicketStatusEnum = Field(..., description="Ticket status")
    decided_by: str | None = Field(default=None, description="Deciding operator identity")
    decision_reason: str | None = Field(default=None, description="Reason for decision")
    notification_channels: list[ChannelNotificationTargetSchema] = Field(default_factory=list, description="Channels notified")


class ApproveTicketRequest(BaseModel):
    """Payload to approve a ticket."""

    decided_by: str = Field(..., min_length=1, description="Approving operator username/id")
    decision_reason: str = Field(default="Approved via channel", description="Approval justification")


class ApproveTicketResponse(BaseModel):
    """Result of ticket approval."""

    ticket: ApprovalTicketResponse = Field(..., description="Updated ticket descriptor")
    execution_token: str = Field(..., description="Single-use execution authorization token")


class RejectTicketRequest(BaseModel):
    """Payload to reject a ticket."""

    decided_by: str = Field(..., min_length=1, description="Rejecting operator username/id")
    decision_reason: str = Field(default="Rejected by operator", description="Rejection rationale")


class ConsumeTokenRequest(BaseModel):
    """Payload to consume single-use execution grant."""

    token: str = Field(..., min_length=1, description="One-time execution token")


class ConsumeTokenResponse(BaseModel):
    """Outcome of token consumption."""

    is_valid: bool = Field(..., description="True if token was valid and unconsumed")
    matched_ticket_id: str | None = Field(default=None, description="Associated ticket ID if valid")


class SessionScopeUpdateRequest(BaseModel):
    """Payload to explicitly configure a session's trust scope."""

    scope: EventTrustScopeEnum = Field(..., description="Desired trust scope")


class SessionScopeResponse(BaseModel):
    """Response containing session's active trust scope."""

    session_id: str = Field(..., description="Session identifier")
    active_scope: EventTrustScopeEnum = Field(..., description="Active trust scope")


class CapabilityAttenuationMetricsResponse(BaseModel):
    """Cumulative operational metrics for event attenuation and async approval bridge."""

    total_events_received: int = Field(..., ge=0)
    verified_events_count: int = Field(..., ge=0)
    rejected_signature_events: int = Field(..., ge=0)
    attenuated_executions_count: int = Field(..., ge=0)
    tickets_created: int = Field(..., ge=0)
    tickets_approved: int = Field(..., ge=0)
    tickets_rejected: int = Field(..., ge=0)
    tickets_expired: int = Field(..., ge=0)
