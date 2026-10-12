"""Pydantic schemas for Granular Workspace Path RBAC & Denial Audit.

[INPUT]
- Web requests defining workspace path policies, checking file permissions, and querying audit ledgers.

[OUTPUT]
- Serialized verdicts, UI denial cards, and structured filesystem audit records.

[POS]
- Server-side DTO contracts for enterprise path RBAC segregation and triple write protection.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class PathRuleDto(BaseModel):
    """Specification of a path pattern and associated access mode."""

    pattern: str = Field(description="Glob pattern for relative path (e.g. 'raw_data/*')")
    mode: Literal["ro", "rw", "none"] = Field(
        default="ro", description="Access mode: 'ro' (Read-Only), 'rw' (Read-Write), 'none'"
    )
    description: str = Field(default="", description="Optional human-readable description")


class WorkspacePolicyDto(BaseModel):
    """Declarative workspace path permission policy."""

    policy_id: str = Field(description="Unique policy identifier")
    user_identity: str = Field(description="Enterprise user identity or SSO principal")
    project_root: str = Field(default=".", description="Root directory of workspace")
    rules: list[PathRuleDto] = Field(
        default_factory=list, description="Ordered list of path permission rules"
    )
    allowed_deliverables_dir: str = Field(
        default="deliverables", description="Designated output directory for deliverables"
    )


class RegisterWorkspacePolicyRequest(BaseModel):
    """Request payload to register or update workspace policy."""

    policy: WorkspacePolicyDto = Field(description="Workspace policy configuration")


class CheckPathAccessRequest(BaseModel):
    """Request payload to test file operation permissions."""

    policy_id: str = Field(description="Target workspace policy identifier")
    agent_id: str = Field(description="Agent identifier executing the operation")
    session_id: str = Field(description="Session or conversation identifier")
    user_identity: str = Field(description="Enterprise user identity context")
    relative_path: str = Field(description="Target relative file or folder path")
    action: Literal["READ", "DIRECT_WRITE", "COPY_WRITE", "MKDIR", "DELETE"] = Field(
        description="Attempted filesystem action"
    )


class WriteDenialCardDto(BaseModel):
    """Visual security denial card with auto-reroute suggestions."""

    title: str = Field(description="Card title")
    message: str = Field(description="Explanation of the security denial")
    blocked_path: str = Field(description="Target path that was denied")
    action: str = Field(description="Action that was attempted")
    suggested_redirect_path: str = Field(
        description="Authorized path where files should be directed"
    )


class CheckPathAccessResponse(BaseModel):
    """Access verdict produced by zero-trust path guard."""

    allowed: bool = Field(description="Whether the operation is permitted")
    effective_mode: str = Field(description="Resolved path permission mode")
    violation_reason: str | None = Field(
        default=None, description="Reason code if operation was denied"
    )
    auto_reroute_hint: str | None = Field(
        default=None, description="Guidance instructing agent where to redirect deliverables"
    )
    denial_card: WriteDenialCardDto | None = Field(
        default=None, description="UI alert card when write denial is triggered"
    )


class AuditLedgerEntryDto(BaseModel):
    """Structured filesystem operation audit record."""

    entry_id: str = Field(description="Unique audit record identifier")
    timestamp: float = Field(description="Unix timestamp")
    agent_id: str = Field(description="Executing agent identifier")
    session_id: str = Field(description="Session identifier")
    user_identity: str = Field(description="Enterprise user identity")
    target_path: str = Field(description="Target relative path")
    action: str = Field(description="Attempted action")
    granted: bool = Field(description="Whether operation was permitted")
    violation_reason: str | None = Field(
        default=None, description="Violation reason if denied"
    )


class AuditStatsDto(BaseModel):
    """Aggregated audit statistics."""

    total_events: int = Field(description="Total recorded filesystem operations")
    granted_count: int = Field(description="Number of permitted operations")
    denied_count: int = Field(description="Number of blocked operations")
    denials_by_action: dict[str, int] = Field(
        default_factory=dict, description="Denied actions breakdown"
    )
    denials_by_reason: dict[str, int] = Field(
        default_factory=dict, description="Denied reasons breakdown"
    )
