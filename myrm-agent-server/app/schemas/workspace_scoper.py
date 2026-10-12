"""Pydantic schemas for Per-Task Workspace Scoping and Cross-Contamination Guard.

[INPUT]
- None.

[OUTPUT]
- Typed DTO models for task directory binding, access mode switching, path verification, and audit reports.

[POS]
- Server schemas. Exposes typed contracts for client UI and agent runtime workspace containment.
"""

from __future__ import annotations

import time

from pydantic import BaseModel, ConfigDict, Field


class WorkspaceBindingDto(BaseModel):
    """Specification of an active task-to-directory scoping binding."""

    model_config = ConfigDict(extra="forbid")

    task_id: str = Field(..., description="Unique task or session identifier")
    workspace_root: str = Field(..., description="Absolute canonical directory assigned to the task")
    access_mode: str = Field(..., description="Access mode: scoped_strict or full_system_access")
    created_at: float = Field(default_factory=time.time, description="Unix timestamp of binding")


class BindWorkspaceRequest(BaseModel):
    """Payload to bind a task to an isolated directory workspace."""

    model_config = ConfigDict(extra="forbid")

    task_id: str = Field(..., description="Unique task or session identifier")
    workspace_root: str = Field(..., description="Target directory path for task containment")
    access_mode: str = Field(
        default="scoped_strict",
        description="Scoping constraint: scoped_strict (default) or full_system_access",
    )


class UpdateAccessModeRequest(BaseModel):
    """Payload to toggle access confinement mode between strict and full system access."""

    model_config = ConfigDict(extra="forbid")

    access_mode: str = Field(
        ...,
        description="Target access mode: scoped_strict or full_system_access",
    )


class VerifyAccessRequest(BaseModel):
    """Request to verify whether a file path access is permissible for a task."""

    model_config = ConfigDict(extra="forbid")

    target_path: str = Field(..., description="File path intended to be read, written, or listed")
    action: str = Field(default="read", description="Action type: read, write, delete, list")


class VerifyAccessResponse(BaseModel):
    """Verdict of path scoping verification."""

    model_config = ConfigDict(extra="forbid")

    task_id: str = Field(..., description="Task identifier")
    target_path: str = Field(..., description="Normalized target path")
    action: str = Field(..., description="Action evaluated")
    allowed: bool = Field(..., description="Whether the path is accessible without escaping workspace")
    access_mode: str = Field(..., description="Active access mode at evaluation time")


class FileAccessAuditEntryDto(BaseModel):
    """Individual file access audit record."""

    model_config = ConfigDict(extra="forbid")

    entry_id: str = Field(..., description="Audit record ID")
    task_id: str = Field(..., description="Task identifier")
    target_path: str = Field(..., description="Canonical target path")
    action: str = Field(..., description="Action: read, write, delete, list")
    allowed: bool = Field(..., description="Whether the request was allowed")
    violation_reason: str | None = Field(default=None, description="Explanation if blocked")
    timestamp: float = Field(default_factory=time.time, description="Unix timestamp of event")


class WorkspaceAuditReportDto(BaseModel):
    """Complete audit summary of task workspace file activities."""

    model_config = ConfigDict(extra="forbid")

    task_id: str = Field(..., description="Task identifier")
    workspace_root: str = Field(..., description="Root workspace path")
    access_mode: str = Field(..., description="Current access confinement mode")
    total_accesses: int = Field(..., description="Total file access attempts logged")
    violations_count: int = Field(..., description="Total boundary violation attempts blocked")
    modified_files: list[str] = Field(default_factory=list, description="List of files created, edited, or deleted")
    audit_entries: list[FileAccessAuditEntryDto] = Field(default_factory=list, description="Chronological log entries")
    generated_at: float = Field(default_factory=time.time, description="Unix timestamp of report generation")
