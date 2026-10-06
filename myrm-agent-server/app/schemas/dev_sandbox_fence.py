"""Pydantic schemas for Zero-Production-Write Dev Sandbox and Synthetic Data Fence API.

[INPUT]
- Pydantic BaseModel and Field from pydantic.

[OUTPUT]
- Request and response DTO schemas for sandbox inspection and dev mode control.

[POS]
Schema definitions for dev sandbox fence isolation and synthetic data assertions.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class InspectDevOperationRequest(BaseModel):
    """Payload to evaluate a development operation against sandbox fence rules."""

    operation_type: str = Field(
        ...,
        description="Operation kind: 'sql', 'git_branch', 'file_write', or 'db_connect'",
    )
    target: str = Field(
        ...,
        description="Target resource: SQL table, git branch name, file path, or database URI",
    )
    payload: str = Field(
        default="",
        description="Optional payload such as raw SQL statement or script body",
    )
    session_id: str = Field(
        default="default_session",
        description="Session identifier for tracking and alerts",
    )


class InspectDevOperationResponse(BaseModel):
    """Evaluation result for dev operation."""

    allowed: bool = Field(..., description="Whether operation is permitted")
    violation_type: str | None = Field(
        default=None, description="Violation classification if blocked or substituted"
    )
    reason: str = Field(..., description="Enforcement rationale or reason")
    substituted_target: str | None = Field(
        default=None,
        description="Substituted synthetic fixture URI if production DB was redirected",
    )


class RegisterSyntheticFixtureRequest(BaseModel):
    """Payload to register an approved synthetic data fixture."""

    fixture_id: str = Field(..., description="Unique fixture identifier")
    database_type: str = Field(..., description="Database engine type: sqlite, postgres, mysql")
    read_only_uri: str = Field(..., description="Read-only connection URI for synthetic replica")
    sample_count: int = Field(default=100, description="Approximate sample records count")
    description: str = Field(default="", description="Dataset description")


class SyntheticFixtureResponse(BaseModel):
    """Details of a registered synthetic data fixture."""

    fixture_id: str
    database_type: str
    read_only_uri: str
    sample_count: int
    description: str


class DevPolicyResponse(BaseModel):
    """Current dev sandbox policy configuration."""

    allowed_branch_prefixes: list[str]
    blocked_branches: list[str]
    allowed_write_directories: list[str]
    blocked_sensitive_patterns: list[str]
    enforce_synthetic_data: bool
    mode: str


class SetDevModeRequest(BaseModel):
    """Payload to set execution environment mode."""

    mode: str = Field(
        ...,
        description="Execution mode: 'dev_isolated', 'readonly_research', or 'production_controlled'",
    )


class DevViolationAlertResponse(BaseModel):
    """Audit alert for a dev sandbox boundary violation."""

    alert_id: str
    session_id: str
    operation_type: str
    violation_type: str
    reason: str
    target: str
    timestamp: datetime
