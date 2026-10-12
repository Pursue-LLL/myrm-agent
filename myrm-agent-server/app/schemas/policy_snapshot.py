"""Pydantic schemas for In-Flight Policy Snapshot Pinning & Non-Silent Drift.

[INPUT]
- None.

[OUTPUT]
- Typed DTO models for policy snapshots, dual-track updates (Soft Update / Emergency Hot Kill),
  and in-flight tool authorization assertions.

[POS]
- Server schemas. Exposes typed contracts for client UI and administrative governance.
"""

from __future__ import annotations

from typing import Union

from pydantic import BaseModel, ConfigDict, Field

JsonScalar = Union[str, int, float, bool, None]


class ExecutionPolicySnapshotDto(BaseModel):
    """Snapshot of governance policy pinned to in-flight tasks."""

    model_config = ConfigDict(extra="forbid")

    snapshot_id: str = Field(..., description="Unique snapshot identifier")
    version_number: int = Field(..., description="Monotonically increasing version number")
    policy_snapshot_hash: str = Field(..., description="Canonical SHA-256 fingerprint of policy")
    prompt_template_hash: str = Field(..., description="SHA-256 hash of system prompt template")
    allowed_tools: list[str] = Field(..., description="List of permitted tool names")
    governance_rules: dict[str, JsonScalar] = Field(
        default_factory=dict, description="Active governance parameter rules"
    )
    created_at: str = Field(..., description="ISO 8601 UTC creation timestamp")


class EmergencyHotKillDirectiveDto(BaseModel):
    """Emergency directive immediately blocking specific high-risk tools across in-flight tasks."""

    model_config = ConfigDict(extra="forbid")

    directive_id: str = Field(..., description="Unique directive identifier")
    revoked_tools: list[str] = Field(..., description="List of revoked tool names")
    reason: str = Field(..., description="Emergency reason justification")
    issued_at: str = Field(..., description="ISO 8601 UTC issue timestamp")
    is_active: bool = Field(default=True, description="Whether directive is currently enforcing")


class TaskPolicyBindingDto(BaseModel):
    """Association pinning an execution policy snapshot to a specific running task."""

    model_config = ConfigDict(extra="forbid")

    task_id: str = Field(..., description="Target task identifier")
    snapshot: ExecutionPolicySnapshotDto = Field(..., description="Pinned policy snapshot")
    bound_at: str = Field(..., description="ISO 8601 UTC binding timestamp")


class BindTaskPolicyRequest(BaseModel):
    """Payload to bind a task to the current active policy snapshot."""

    model_config = ConfigDict(extra="forbid")

    task_id: str = Field(..., description="Unique task identifier to pin")


class SoftUpdatePolicyRequest(BaseModel):
    """Payload to apply a Track A Soft Update (affects new tasks only)."""

    model_config = ConfigDict(extra="forbid")

    prompt_template: str = Field(..., description="New system prompt template")
    allowed_tools: list[str] = Field(..., description="Updated permitted tool list")
    governance_rules: dict[str, JsonScalar] = Field(
        default_factory=dict, description="Updated governance parameter rules"
    )


class EmergencyHotKillRequest(BaseModel):
    """Payload to apply a Track B Emergency Hot Kill (immediately halts in-flight tasks)."""

    model_config = ConfigDict(extra="forbid")

    revoked_tools: list[str] = Field(..., description="Tool names to revoke with immediate effect")
    reason: str = Field(..., description="Emergency justification / incident reason")


class RevokeEmergencyHotKillRequest(BaseModel):
    """Payload to revoke an active emergency hot-kill directive."""

    model_config = ConfigDict(extra="forbid")

    directive_id: str = Field(..., description="Directive identifier to revoke")


class AssertToolExecutionRequest(BaseModel):
    """Payload to assert whether a tool call is authorized under a task's pinned policy."""

    model_config = ConfigDict(extra="forbid")

    task_id: str = Field(..., description="Target in-flight task identifier")
    tool_name: str = Field(..., description="Tool name intended for execution")


class AssertToolExecutionResponse(BaseModel):
    """Outcome of tool authorization check under in-flight policy pinning."""

    model_config = ConfigDict(extra="forbid")

    allowed: bool = Field(..., description="True if tool is permitted to execute")
    task_id: str = Field(..., description="Evaluated task identifier")
    tool_name: str = Field(..., description="Evaluated tool name")
    snapshot_version: int | None = Field(default=None, description="Pinned snapshot version number")
    snapshot_hash: str | None = Field(default=None, description="Pinned snapshot fingerprint")
    blocked_reason: str | None = Field(default=None, description="Reason if blocked")
