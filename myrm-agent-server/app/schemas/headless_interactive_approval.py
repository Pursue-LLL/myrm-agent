"""Pydantic schemas for Headless Agent Interactive Approval, Webhook Relay, and Hold-Resume Suite.

[POS] app/schemas/headless_interactive_approval.py
[INPUT] pydantic
[OUTPUT] RiskActionDTO, CreateHoldTicketRequest, HoldTicketDTO, SubmitApprovalDecisionRequest, SubmitApprovalDecisionResponse, WebhookEndpointConfigRequest, WebhookRelayPayloadDTO, FormatStreamHoldNoticeRequest, StreamHoldChunkDTO
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class RiskActionDTO(BaseModel):
    """Data transfer object describing a high-risk action requiring approval."""

    model_config = ConfigDict(frozen=True)

    action_id: str = Field(..., description="Unique action identifier")
    tool_name: str = Field(..., description="Target tool or skill name (e.g. bash, db_exec)")
    command_or_target: str = Field(..., description="Raw command or affected entity")
    risk_level: str = Field(default="CRITICAL", description="Risk level (CRITICAL, HIGH, MEDIUM)")
    justification: str = Field(default="", description="Reasoning or intent behind the requested action")


class CreateHoldTicketRequest(BaseModel):
    """Request payload to create an execution hold ticket and generate an approval shortlink."""

    model_config = ConfigDict(frozen=True)

    session_id: str = Field(..., description="Active session ID")
    action: RiskActionDTO = Field(..., description="Risk action descriptor")
    timeout_seconds: float = Field(default=300.0, description="Expiration time window in seconds")


class HoldTicketDTO(BaseModel):
    """Data transfer object representing an ephemeral approval hold ticket."""

    model_config = ConfigDict(frozen=True)

    tx_id: str
    session_id: str
    action: RiskActionDTO
    status: str
    shortlink_url: str
    created_at: float
    expires_at: float
    operator_decision_notes: str | None = None
    decided_by: str | None = None
    decided_at: float | None = None


class SubmitApprovalDecisionRequest(BaseModel):
    """Request payload to record an operator decision on a hold ticket."""

    model_config = ConfigDict(frozen=True)

    decision: str = Field(..., description="Decision outcome (APPROVED, REJECTED)")
    operator: str = Field(default="human_operator", description="Identity of the operator submitting approval")
    notes: str | None = Field(default=None, description="Optional decision notes or justification")


class SubmitApprovalDecisionResponse(BaseModel):
    """Result of submitting an operator approval decision."""

    model_config = ConfigDict(frozen=True)

    ticket: HoldTicketDTO
    resumed: bool


class WebhookEndpointConfigRequest(BaseModel):
    """Request payload to register an outbound notification webhook endpoint."""

    model_config = ConfigDict(frozen=True)

    name: str = Field(..., description="Endpoint identifier (e.g. secops_telegram, dev_feishu)")
    url: str = Field(..., description="Outbound webhook URL")


class WebhookRelayPayloadDTO(BaseModel):
    """Standardized payload dispatched to external messaging channels."""

    model_config = ConfigDict(frozen=True)

    tx_id: str
    session_id: str
    tool_name: str
    command_or_target: str
    risk_level: str
    approval_shortlink: str
    expires_in_seconds: int
    custom_metadata: dict[str, str]


class FormatStreamHoldNoticeRequest(BaseModel):
    """Request payload to render in-stream markdown notice for SSE streaming reasoning."""

    model_config = ConfigDict(frozen=True)

    tx_id: str = Field(..., description="Transaction hold ticket ID")
    is_resumed: bool = Field(default=False, description="True if formatting resumed state block")


class StreamHoldChunkDTO(BaseModel):
    """Formatted markdown notice for SSE streaming reasoning."""

    model_config = ConfigDict(frozen=True)

    tx_id: str
    inject_markdown: str
    is_resumed: bool
    status: str
