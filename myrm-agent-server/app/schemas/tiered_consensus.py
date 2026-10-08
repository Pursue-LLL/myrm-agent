"""Pydantic schemas and DTOs for Tiered Memory Hierarchy & Proposed Consensus Flow (Item 114).

[INPUT]
- pydantic::{BaseModel, Field} (POS: validated request and response models)

[OUTPUT]
- TieredMemoryRecordDTO, ConsensusAuditLogDTO: tiered record and consensus audit entry
- ProposeRecordRequest, ReviewProposalRequest, RevokeConsensusRequest: proposal, review and revocation requests

[POS]
API contracts of tiered memory consensus, shared by its router and service.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class TieredMemoryRecordDTO(BaseModel):
    """DTO representing a scoped memory record governed by consensus lifecycle."""

    record_id: str = Field(description="Unique system identifier for the memory record")
    scope_tier: str = Field(description="Boundary scope tier: personal, project, or team_consensus")
    content: str = Field(description="Normative memory statement or guideline")
    content_fingerprint: str = Field(description="Deterministic SHA-256 fingerprint for deduplication")
    owner_peer_id: str = Field(description="Originating peer id (human user or proposing agent)")
    project_id: str | None = Field(default=None, description="Optional project workspace identifier")
    status: str = Field(description="Lifecycle status: proposed, approved, rejected, revoked")
    version: int = Field(default=1, description="Sequential version counter")
    superseded_by: str | None = Field(default=None, description="Record ID of newer consensus replacing this one")
    rationale: str = Field(default="", description="Originating justification or evidence")
    created_at: str = Field(description="Creation ISO timestamp")
    updated_at: str = Field(description="Last updated ISO timestamp")


class ConsensusAuditLogDTO(BaseModel):
    """DTO representing an immutable consensus lifecycle audit log entry."""

    audit_id: str = Field(description="Unique audit entry identifier")
    record_id: str = Field(description="Target memory record identifier")
    action: str = Field(description="Transition action: propose, approve, reject, revoke")
    operator_peer_id: str = Field(description="Peer ID executing the action")
    reason: str = Field(default="", description="Operator rationale or justification")
    timestamp: str = Field(description="Event ISO timestamp")


class ProposeRecordRequest(BaseModel):
    """Request payload to propose or persist a new tiered memory record."""

    scope_tier: str = Field(
        default="personal",
        description="Scope tier: personal, project, or team_consensus",
    )
    content: str = Field(min_length=1, description="Normative statement or guideline content")
    owner_peer_id: str = Field(min_length=1, description="Originating peer id")
    project_id: str | None = Field(default=None, description="Project workspace identifier (required if tier=project)")
    rationale: str = Field(default="", description="Optional context or rationale")
    auto_approve_personal_project: bool = Field(
        default=True,
        description="Whether to auto-approve personal and project tier records immediately",
    )


class ReviewProposalRequest(BaseModel):
    """Request payload to approve or reject a proposed consensus draft."""

    approver_peer_id: str = Field(min_length=1, description="Approver human user or administrator peer id")
    reason: str = Field(default="", description="Reviewer decision rationale or evidence")


class RevokeConsensusRequest(BaseModel):
    """Request payload to retire an active team consensus record."""

    operator_peer_id: str = Field(min_length=1, description="Operator peer id performing revocation")
    reason: str = Field(default="", description="Revocation justification")
    superseded_by: str | None = Field(default=None, description="Optional replacement consensus record id")
