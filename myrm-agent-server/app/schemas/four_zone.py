"""Pydantic schemas for Four-Zone Workspace Layout and Read-Only Source Protection.

[INPUT]
None.

[OUTPUT]
DTO models for 4-zone scaffolding, permission checks, safe replication, and artifact promotion.

[POS]
Server schemas. Exposes typed contracts for client workspaces to maintain physical
zone boundaries, protect original assets, and enforce one-way deliverable flow.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class FourZoneInitRequest(BaseModel):
    """Request payload to initialize standard 4-zone directory layout."""

    model_config = ConfigDict(extra="forbid")

    workspace_root: str = Field(..., description="Absolute directory path of workspace root")


class FourZoneInitResponse(BaseModel):
    """Response payload containing created four zones."""

    model_config = ConfigDict(extra="forbid")

    zones: dict[str, str] = Field(..., description="Map of zone names to absolute directory paths")
    status: str = Field(..., description="Initialization status: success, exists, error")
    message: str = Field(..., description="Human-readable summary message")


class FourZoneCheckRequest(BaseModel):
    """Request to validate whether an operation violates zone invariants."""

    model_config = ConfigDict(extra="forbid")

    file_path: str = Field(..., description="Target file path to evaluate")
    operation: Literal["read", "write", "delete", "rename", "promote"] = Field(
        ..., description="Requested file operation category"
    )


class FourZoneCheckResponse(BaseModel):
    """Evaluation verdict for target file path and operation."""

    model_config = ConfigDict(extra="forbid")

    allowed: bool = Field(..., description="Whether the operation is permitted")
    zone: str | None = Field(default=None, description="Identified workspace zone name")
    reason: str = Field(..., description="Policy decision explanation")


class FourZoneReplicateRequest(BaseModel):
    """Request to safely replicate raw Zone 01 original into Zone 02 draft."""

    model_config = ConfigDict(extra="forbid")

    workspace_root: str = Field(..., description="Workspace root path")
    source_rel_path: str = Field(..., description="Relative path within Zone 01 (原始材料)")
    draft_rel_path: str = Field(..., description="Destination relative path within Zone 02 (过程草稿)")


class FourZoneReplicateResponse(BaseModel):
    """Result of replicating original document to draft zone."""

    model_config = ConfigDict(extra="forbid")

    draft_full_path: str = Field(..., description="Full path to newly created draft replica")
    message: str = Field(..., description="Operation confirmation message")


class FourZonePromotionRequest(BaseModel):
    """Request to promote artifact forward across workspace zones."""

    model_config = ConfigDict(extra="forbid")

    workspace_root: str = Field(..., description="Workspace root path")
    source_rel_path: str = Field(..., description="Source relative path within origin zone")
    target_rel_path: str = Field(..., description="Target relative path within destination zone")
    promotion_type: Literal["draft_to_canonical", "canonical_to_deliverable"] = Field(
        ..., description="Promotion stage: 02->03 (draft_to_canonical) or 03->04 (canonical_to_deliverable)"
    )
    reviewer_id: str = Field(..., description="Identifier of the operator authorizing promotion")


class FourZonePromotionResponse(BaseModel):
    """Audit record of successful artifact promotion."""

    model_config = ConfigDict(extra="forbid")

    promotion_id: str = Field(..., description="Unique promotion audit identifier")
    source_zone: str = Field(..., description="Source zone name")
    target_zone: str = Field(..., description="Target zone name")
    source_path: str = Field(..., description="Source file path")
    target_path: str = Field(..., description="Target file path")
    promoted_by: str = Field(..., description="Reviewer identifier")
    promoted_at: float = Field(..., description="Epoch timestamp of promotion")
