"""[INPUT]
None
[OUTPUT]
Pydantic schemas for Multi-Client Bidirectional Approval Protocol and Visual Diff Payloads.
[POS]
app/services/approvals/bidirectional/protocol_types.py
"""

from typing import Literal, Optional

from pydantic import BaseModel, Field

ApprovalActionKind = Literal["file_write", "command_exec", "tool_call", "outbound_request"]
RiskSeverity = Literal["low", "medium", "high", "critical"]
DecisionKind = Literal["allow", "reject", "remember_session"]
ClientType = Literal["web", "desktop", "mobile"]


class FileDiffPayload(BaseModel):
    """Structured code and file modification diff payload."""

    file_path: str = Field(description="Target file relative or absolute path")
    old_content: Optional[str] = Field(default=None, description="Previous file content before edit")
    new_content: str = Field(description="Proposed new file content")
    unified_diff: str = Field(description="Unified format diff string")
    added_lines: int = Field(default=0, description="Total count of added lines")
    removed_lines: int = Field(default=0, description="Total count of removed lines")
    is_new_file: bool = Field(default=False, description="True if target file does not previously exist")
    is_deletion: bool = Field(default=False, description="True if file is being deleted")


class CommandRiskPayload(BaseModel):
    """Structured terminal shell command execution risk analysis."""

    command: str = Field(description="Command line string to be executed")
    cwd: str = Field(description="Working directory for command execution")
    risk_severity: RiskSeverity = Field(description="Assessed risk severity level")
    risk_reasons: list[str] = Field(default_factory=list, description="Specific safety violation reasons")
    blast_radius_paths: list[str] = Field(
        default_factory=list, description="File paths potentially impacted by execution"
    )


class StructuredApprovalRequest(BaseModel):
    """Bidirectional structured approval request sent from Server to Clients."""

    approval_id: str = Field(description="Unique deterministic approval identifier")
    session_id: str = Field(description="Active conversation or run session ID")
    sequence_id: int = Field(description="Monotonically increasing sequence number for ACK and dedup")
    kind: ApprovalActionKind = Field(description="Classification of action requiring approval")
    summary: str = Field(description="Human readable action summary")
    file_diff: Optional[FileDiffPayload] = Field(default=None, description="Detailed file diff if applicable")
    command_risk: Optional[CommandRiskPayload] = Field(
        default=None, description="Detailed command risk analysis if applicable"
    )
    created_at: float = Field(description="Request epoch timestamp")
    expires_at: Optional[float] = Field(default=None, description="Timeout expiration epoch timestamp")
    allowed_decisions: list[DecisionKind] = Field(
        default=["allow", "reject", "remember_session"],
        description="Allowed decision options",
    )


class StructuredApprovalDecision(BaseModel):
    """Decision payload transmitted from Client to Server."""

    approval_id: str = Field(description="Identifier of target approval request")
    decision: DecisionKind = Field(description="Client decision: allow, reject, or remember_session")
    decided_by: str = Field(default="user", description="Identity or operator who made decision")
    client_type: ClientType = Field(default="web", description="Originating client platform")
    reason: Optional[str] = Field(default=None, description="Optional user provided rationale")
    decided_at: float = Field(description="Decision epoch timestamp")


class ApprovalAck(BaseModel):
    """Server acknowledgment receipt ensuring bidirectional transport reliability."""

    approval_id: str = Field(description="Target approval ID")
    sequence_id: int = Field(description="Sequence number acknowledged")
    acknowledged: bool = Field(description="True if server accepted decision")
    status: str = Field(description="Current status: resolved, expired, or rejected")
