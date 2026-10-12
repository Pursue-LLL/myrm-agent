"""Pydantic schemas for Managed Permission Template Presets, Session Checkpoint Rollback, and Connectors Hub.

[POS] app/schemas/managed_permission_rollback.py
[INPUT] pydantic
[OUTPUT] RolePermissionPolicyDTO, ComplianceDriftCheckRequest, ComplianceDriftResponse, CreateSessionCheckpointRequest, SessionCheckpointDTO, RollbackSessionCheckpointRequest, RollbackSessionCheckpointResponse, RegisterConnectorRequest, ManagedConnectorMetaDTO
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class RolePermissionPolicyDTO(BaseModel):
    """Data transfer object describing an enterprise permission template preset."""

    model_config = ConfigDict(frozen=True)

    role: str
    display_name: str
    description: str
    rules: dict[str, str]
    max_network_egress_domains: int
    allow_shell_execution: bool
    require_hitl_on_external_sends: bool
    allowed_filesystem_roots: list[str]


class ComplianceDriftItemDTO(BaseModel):
    """Specific permission drift item against baseline template."""

    model_config = ConfigDict(frozen=True)

    target: str
    template_rule: str
    actual_rule: str
    is_excessive: bool
    remediation_hint: str


class ComplianceDriftCheckRequest(BaseModel):
    """Request payload to evaluate privilege drift against a designated role template."""

    model_config = ConfigDict(frozen=True)

    agent_id: str = Field(..., description="Target agent profile or instance identifier")
    assigned_role: str = Field(..., description="Designated canonical enterprise role (e.g. AUDITOR, SAFE_COLLABORATOR)")
    active_rules: dict[str, str] = Field(..., description="Active runtime dimension enforcement rules")
    active_allow_shell: bool = Field(default=False, description="Whether shell execution is currently enabled")


class ComplianceDriftResponse(BaseModel):
    """Evaluation result reporting compliance state and deviations."""

    model_config = ConfigDict(frozen=True)

    agent_id: str
    assigned_role: str
    is_compliant: bool
    drift_score: float
    deviations: list[ComplianceDriftItemDTO]


class CreateSessionCheckpointRequest(BaseModel):
    """Request payload to capture an atomic session checkpoint."""

    model_config = ConfigDict(frozen=True)

    session_id: str = Field(..., description="Active session identifier")
    label: str = Field(..., description="Milestone or task stage label for this checkpoint")
    files: dict[str, str] = Field(default_factory=dict, description="Map of relative file paths to UTF-8 file content")
    memory_state: dict[str, str] = Field(default_factory=dict, description="Key-value state dictionary of short-term memory")
    active_role: str = Field(default="SAFE_COLLABORATOR", description="Active role template at checkpoint time")


class SessionCheckpointDTO(BaseModel):
    """Metadata representing a persisted session checkpoint."""

    model_config = ConfigDict(frozen=True)

    checkpoint_id: str
    session_id: str
    label: str
    created_at: float
    files_count: int
    memory_keys_count: int
    active_role: str


class RollbackSessionCheckpointRequest(BaseModel):
    """Request payload to restore workspace and session memory to a historical checkpoint."""

    model_config = ConfigDict(frozen=True)

    checkpoint_id: str = Field(..., description="Target historical checkpoint identifier to roll back to")
    current_files: dict[str, str] = Field(default_factory=dict, description="Current workspace files before rollback")


class RollbackSessionCheckpointResponse(BaseModel):
    """Outcome of atomic checkpoint rollback including diff summary and restored state."""

    model_config = ConfigDict(frozen=True)

    checkpoint_id: str
    session_id: str
    reverted_files_count: int
    restored_memory_keys_count: int
    modified_paths: list[str]
    rolled_back_at: float
    restored_files: dict[str, str]
    restored_memory_state: dict[str, str]


class RegisterConnectorRequest(BaseModel):
    """Request payload to register an external channel connector into the hub."""

    model_config = ConfigDict(frozen=True)

    connector_id: str = Field(..., description="Unique connector identifier")
    channel_type: str = Field(..., description="Integration channel (DISCORD, GITHUB, SLACK, NOTION, JIRA, FEISHU)")
    display_name: str = Field(..., description="Human-friendly label")
    account_identifier: str = Field(default="", description="Target team or organization account identifier")
    token_lifetime_seconds: float | None = Field(default=3600.0, description="OAuth or token lifetime in seconds")


class ManagedConnectorMetaDTO(BaseModel):
    """Metadata and health posture of an external channel connector."""

    model_config = ConfigDict(frozen=True)

    connector_id: str
    channel_type: str
    display_name: str
    status: str
    last_heartbeat_at: float
    token_expires_at: float | None = None
    account_identifier: str
