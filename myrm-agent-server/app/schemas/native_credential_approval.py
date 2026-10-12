"""Pydantic schemas for Native Credential Approvals and Precise Message Links.

[INPUT]
- None.

[OUTPUT]
- Typed DTO models for creating, deciding, and querying native credential access approvals.

[POS]
- Server schemas for QM #1502 native credential approval and session message linking.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class MessageSequenceRefDto(BaseModel):
    """Contextual coordinate linking a credential request to a conversation turn."""

    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(..., description="Target session or conversation ID")
    message_id: str = Field(..., description="Specific triggering message ID")
    sequence_number: int = Field(
        ..., ge=0, description="Exact monotonic message sequence number"
    )
    turn_index: int | None = Field(
        default=None, description="Optional conversational turn index"
    )


class PreciseMessageLinkDto(BaseModel):
    """Standardized navigation deep link targeting a specific message in the UI transcript."""

    model_config = ConfigDict(extra="forbid")

    path: str = Field(..., description="Base route path to the conversation")
    sequence_number: int = Field(..., description="Target sequence number")
    message_id: str = Field(..., description="Target message ID")
    deep_link_url: str = Field(..., description="Complete URL query with sequence anchors")


class CreateCredentialAskRequest(BaseModel):
    """Payload to request access to a protected credential via native approval."""

    model_config = ConfigDict(extra="forbid")

    credential_id: str = Field(..., description="Identifier of the requested credential")
    service_name: str = Field(..., description="External service name (e.g. GitHub, AWS, Stripe)")
    account_label: str = Field(..., description="Account or environment label")
    requester_id: str = Field(..., description="Agent or tool requesting access")
    owner_id: str = Field(..., description="Credential owner authorized to grant access")
    purpose: str = Field(..., description="Action purpose presented to approver")
    session_id: str = Field(..., description="Conversation session ID triggering request")
    message_id: str = Field(..., description="Exact message ID triggering request")
    sequence_number: int = Field(..., ge=0, description="Exact message sequence index")
    turn_index: int | None = Field(default=None, description="Optional turn index")


class DecideCredentialAskRequest(BaseModel):
    """Payload to approve or deny a pending credential request."""

    model_config = ConfigDict(extra="forbid")

    decider_id: str = Field(..., description="User ID of the approving principal")
    decision: str = Field(
        ...,
        description="Decision mode: 'once' (single turn), 'standing' (session-wide), or 'deny'",
    )
    note: str = Field(default="", description="Optional operator rationale or note")


class CredentialAskDto(BaseModel):
    """Details of a native credential access approval request."""

    model_config = ConfigDict(extra="forbid")

    ask_id: str = Field(..., description="Unique ask identifier")
    credential_id: str = Field(..., description="Identifier of the requested credential")
    service_name: str = Field(..., description="Service name")
    account_label: str = Field(..., description="Account label")
    requester_id: str = Field(..., description="Requesting agent or tool ID")
    owner_id: str = Field(..., description="Credential owner ID")
    purpose: str = Field(..., description="Request purpose")
    message_ref: MessageSequenceRefDto = Field(..., description="Message coordinates")
    deep_link: PreciseMessageLinkDto = Field(..., description="Precise message deep link")
    status: str = Field(..., description="Status: pending, approved, denied, expired, cancelled")
    decision_mode: str | None = Field(default=None, description="Decision mode once decided")
    decided_by: str | None = Field(default=None, description="Principal who decided")
    decision_note: str | None = Field(default=None, description="Decision note")
    created_at_iso: str = Field(..., description="Creation ISO timestamp")
    decided_at_iso: str | None = Field(default=None, description="Decision ISO timestamp")


class ApprovalAuditRecordDto(BaseModel):
    """Immutable audit entry for credential access approvals."""

    model_config = ConfigDict(extra="forbid")

    audit_id: str = Field(..., description="Unique audit record ID")
    ask_id: str = Field(..., description="Referenced ask ID")
    credential_id: str = Field(..., description="Credential ID")
    service_name: str = Field(..., description="Service name")
    actor_id: str = Field(..., description="Acting decider ID")
    decision: str = Field(..., description="Decision made (once, standing, deny)")
    target_session_id: str = Field(..., description="Session ID")
    sequence_number: int = Field(..., description="Sequence number")
    timestamp_iso: str = Field(..., description="Timestamp ISO string")
    note: str = Field(default="", description="Audit note")


class DecideCredentialAskResponse(BaseModel):
    """Response returned upon deciding a credential ask."""

    model_config = ConfigDict(extra="forbid")

    ask: CredentialAskDto = Field(..., description="Updated ask entity")
    audit_record: ApprovalAuditRecordDto = Field(..., description="Generated audit record")


class PendingAsksResponse(BaseModel):
    """Response containing a list of pending credential approval requests."""

    model_config = ConfigDict(extra="forbid")

    pending_asks: list[CredentialAskDto] = Field(
        default_factory=list, description="List of pending asks"
    )
    total_count: int = Field(..., description="Total count of pending requests")
