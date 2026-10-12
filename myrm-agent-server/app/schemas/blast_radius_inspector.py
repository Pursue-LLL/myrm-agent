"""Pydantic schemas for Agent Blast Radius Static Inspector and Action Surface Guard Attribution.

[POS] app/schemas/blast_radius_inspector.py
[INPUT] pydantic
[OUTPUT] ActionSurfaceInspectRequest, ActionSurfaceExposureReportDTO, GuardAttributionRequest, GuardAttributionResponse, AutoRepairPatchRequest, RepairPolicyPatchDTO, ToggleKillSwitchRequest, KillSwitchStatusResponse
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class SinkVulnerabilityDTO(BaseModel):
    """Data transfer object for a static action sink vulnerability."""

    model_config = ConfigDict(frozen=True)

    action_category: str
    dimension: str
    sink_identifier: str
    danger_tier: str
    description: str


class ActionSurfaceInspectRequest(BaseModel):
    """Request payload to statically inspect an agent profile's action surface."""

    model_config = ConfigDict(frozen=True)

    profile_id: str = Field(default="default_agent_profile", description="Unique agent profile or role ID")
    tools: list[str] = Field(default_factory=list, description="Registered tool identifiers")
    declared_file_scopes: list[str] = Field(default_factory=list, description="Allowed or declared filesystem paths")
    declared_api_endpoints: list[str] = Field(default_factory=list, description="Allowed external HTTP/REST endpoints")
    declared_send_channels: list[str] = Field(default_factory=list, description="Allowed external communication sinks")
    installed_plugins: list[str] = Field(default_factory=list, description="Installed third-party plugin identifiers")


class ActionSurfaceExposureReportDTO(BaseModel):
    """Inspection report detailing static exposure surface and pre-admission posture."""

    model_config = ConfigDict(frozen=True)

    profile_id: str
    total_tools_count: int
    total_files_scope_count: int
    total_apis_count: int
    total_sends_count: int
    action_breakdown: dict[str, int]
    reachable_verified_count: int
    install_liability_count: int
    unguarded_critical_count: int
    exposure_score: float
    pre_admission_allowed: bool
    admission_rejection_reason: str | None = None
    sinks: list[SinkVulnerabilityDTO]


class GuardAttributionItemDTO(BaseModel):
    """Attribution item mapping a sink to an active guard and status."""

    model_config = ConfigDict(frozen=True)

    sink: SinkVulnerabilityDTO
    guard_status: str
    assigned_guard_name: str | None = None
    recommended_policy_fix: str | None = None


class GuardAttributionRequest(BaseModel):
    """Request payload to calculate guard attribution and downgraded exposure."""

    model_config = ConfigDict(frozen=True)

    sinks: list[SinkVulnerabilityDTO] = Field(..., description="List of identified action sinks")
    active_guards: dict[str, str] = Field(
        default_factory=dict,
        description="Map of sink_id or dimension to active guard identifier",
    )


class GuardAttributionResponse(BaseModel):
    """Response payload containing guard attribution matrix and summary."""

    model_config = ConfigDict(frozen=True)

    attributions: list[GuardAttributionItemDTO]
    attributed_count: int
    unguarded_count: int
    remediation_required: bool


class RepairPolicyPatchDTO(BaseModel):
    """Synthesized least-privilege repair policy patch for unmitigated sinks."""

    model_config = ConfigDict(frozen=True)

    patch_id: str
    target_sink: str
    injected_guard_type: str
    patch_configuration: dict[str, str]
    rationale: str


class AutoRepairPatchRequest(BaseModel):
    """Request payload to synthesize automatic remediation policy patches."""

    model_config = ConfigDict(frozen=True)

    sinks: list[SinkVulnerabilityDTO] = Field(..., description="Action sinks needing mitigation")
    active_guards: dict[str, str] = Field(
        default_factory=dict,
        description="Currently active guards",
    )


class AutoRepairPatchResponse(BaseModel):
    """Collection of auto-synthesized repair policy patches."""

    model_config = ConfigDict(frozen=True)

    patches: list[RepairPolicyPatchDTO]
    total_patches: int


class ToggleKillSwitchRequest(BaseModel):
    """Request payload to engage or disengage the global outgoing action kill switch."""

    model_config = ConfigDict(frozen=True)

    enabled: bool = Field(..., description="True to engage kill switch, False to disengage")
    reason: str = Field(..., description="Operator justification or incident ID")
    operator: str = Field(default="system_admin", description="Operator identity")


class KillSwitchStatusResponse(BaseModel):
    """Current state of the global action kill switch."""

    model_config = ConfigDict(frozen=True)

    is_engaged: bool
    engaged_by: str | None = None
    reason: str | None = None
    engaged_at: float | None = None
