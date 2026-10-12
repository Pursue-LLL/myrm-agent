"""
[POS] app/schemas/host_execution_guard.py
[INPUT] pydantic, enum
[OUTPUT] PathAccessModeResponse, PathProtectionActionResponse, DestructiveRiskLevelResponse, InspectPathRequest, InspectPathResponse, InspectCommandRequest, InspectCommandResponse, ApproveCommandRequest, RejectCommandRequest, FileSnapshotEntryResponse, WorkspaceSnapshotResponse, CreateSnapshotRequest, RollbackSnapshotRequest, HostExecutionGuardMetricsResponse

Pydantic schemas for Local Host Safe Execution Sandbox & Non-Destructive Guardrail Suite.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class PathAccessModeResponse(StrEnum):
    """File access mode being evaluated."""

    READ = "READ"
    WRITE = "WRITE"
    DELETE = "DELETE"
    EXECUTE = "EXECUTE"


class PathProtectionActionResponse(StrEnum):
    """Enforcement action applied to path operations."""

    ALLOW = "ALLOW"
    VIRTUAL_OVERLAY = "VIRTUAL_OVERLAY"
    BLOCK = "BLOCK"


class DestructiveRiskLevelResponse(StrEnum):
    """Safety risk level determined by AST inspection."""

    SAFE = "SAFE"
    REQUIRE_HITL = "REQUIRE_HITL"
    BLOCKED_DESTRUCTIVE = "BLOCKED_DESTRUCTIVE"


class InspectPathRequest(BaseModel):
    """Payload to inspect host file access safety and redirection."""

    target_path: str = Field(..., min_length=1, description="Target filesystem path")
    mode: PathAccessModeResponse = Field(
        default=PathAccessModeResponse.WRITE,
        description="Access mode (READ, WRITE, DELETE, EXECUTE)",
    )


class InspectPathResponse(BaseModel):
    """Path protection evaluation outcome."""

    original_path: str = Field(..., description="Original input path")
    is_protected: bool = Field(..., description="Whether path falls under protection rules")
    action: PathProtectionActionResponse = Field(..., description="Enforcement action")
    effective_path: str = Field(..., description="Effective safe or redirected target path")
    explanation: str = Field(..., description="Rule justification")


class InspectCommandRequest(BaseModel):
    """Payload to statically inspect shell command safety prior to execution."""

    command: str = Field(..., min_length=1, description="Raw shell command string")


class InspectCommandResponse(BaseModel):
    """Command AST safety inspection outcome."""

    inspection_id: str = Field(..., description="Unique inspection flow ID")
    command: str = Field(..., description="Inspected command")
    risk_level: DestructiveRiskLevelResponse = Field(..., description="Risk category")
    matched_patterns: list[str] = Field(default_factory=list, description="Matched hazard patterns")
    explanation: str = Field(..., description="Decision rationale")
    requires_hitl: bool = Field(..., description="Whether human confirmation is required")
    is_blocked: bool = Field(..., description="Whether command is unconditionally blocked")


class ApproveCommandRequest(BaseModel):
    """Payload to approve a pending high-risk shell command."""

    inspection_id: str = Field(..., min_length=1, description="Inspection ID awaiting approval")


class RejectCommandRequest(BaseModel):
    """Payload to reject a pending high-risk shell command."""

    inspection_id: str = Field(..., min_length=1, description="Inspection ID to reject")


class FileSnapshotEntryResponse(BaseModel):
    """Single file snapshot descriptor."""

    relative_path: str = Field(..., description="Workspace relative path")
    original_hash: str = Field(..., description="Pre-modification SHA-256 hash")
    original_content: str | None = Field(default=None, description="Pre-modification text content")
    is_deleted: bool = Field(default=False, description="True if file did not exist initially")


class WorkspaceSnapshotResponse(BaseModel):
    """Captured workspace snapshot descriptor."""

    snapshot_id: str = Field(..., description="Unique snapshot ID")
    workspace_root: str = Field(..., description="Workspace root directory")
    created_at: float = Field(..., description="Epoch creation timestamp")
    entries: list[FileSnapshotEntryResponse] = Field(..., description="Captured file entries")
    description: str = Field(..., description="Snapshot label or purpose")
    is_restored: bool = Field(default=False, description="True if snapshot was restored")


class CreateSnapshotRequest(BaseModel):
    """Payload to capture pre-write COW snapshot."""

    workspace_root: str = Field(..., min_length=1, description="Target workspace root")
    target_rel_paths: list[str] = Field(..., min_length=1, description="Files about to be touched")
    description: str = Field(
        default="Pre-modification checkpoint",
        description="Snapshot description",
    )


class RollbackSnapshotRequest(BaseModel):
    """Payload to execute atomic rollback."""

    snapshot_id: str = Field(..., min_length=1, description="Snapshot ID to restore")


class HostExecutionGuardMetricsResponse(BaseModel):
    """Cumulative operational metrics for host execution guardrail suite."""

    paths_inspected_total: int = Field(..., ge=0)
    paths_redirected_total: int = Field(..., ge=0)
    paths_blocked_total: int = Field(..., ge=0)
    commands_inspected_total: int = Field(..., ge=0)
    commands_blocked_total: int = Field(..., ge=0)
    hitl_requested_total: int = Field(..., ge=0)
    hitl_approved_total: int = Field(..., ge=0)
    snapshots_created_total: int = Field(..., ge=0)
    rollbacks_executed_total: int = Field(..., ge=0)
