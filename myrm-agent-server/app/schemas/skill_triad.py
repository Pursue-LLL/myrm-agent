"""Pydantic V2 schemas for memory skill triad and physical scope isolation API.

[POS]
Data transfer objects and request/response models for scope physical partitioning,
provider degradation state monitoring, machine CLI envelope formatting,
and repository integration pipeline verification.

[INPUT]
- pydantic::BaseModel, Field

[OUTPUT]
- ScopeCoordinatesDTO
- ResolveScopeRequest
- ScopePartitionResponse
- DeleteScopeRequest
- DeleteScopeResponse
- ProviderAssessRequest
- ProviderDegradedInfoDTO
- DegradedReportResponse
- FormatCliEnvelopeRequest
- CliEnvelopeResponse
- SurveyFindingDTO
- ValidateSurveyRequest
- ValidateSurveyResponse
- VerifySeamsRequest
- VerifySeamsResponse
- SkillTriadHealthResponse
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ScopeCoordinatesDTO(BaseModel):
    """Multi-dimensional coordinates identifying an isolated memory scope."""

    tenant_id: str = Field(default="default_tenant", description="Tenant or organization identifier")
    workspace_id: str = Field(default="default_workspace", description="Workspace or project identifier")
    agent_id: str = Field(default="default_agent", description="Agent persona identifier")
    session_id: str = Field(default="default_session", description="Conversation or session identifier")


class ResolveScopeRequest(BaseModel):
    """Request to resolve physical partition layout for given coordinates."""

    coordinates: ScopeCoordinatesDTO = Field(description="Target scope coordinates")


class ScopePartitionResponse(BaseModel):
    """Filesystem directory and isolated SQLite database paths for a scope."""

    coordinates: ScopeCoordinatesDTO = Field(description="Target scope coordinates")
    namespace_hash: str = Field(description="Collision-resistant length-prefixed namespace hash")
    partition_dir: str = Field(description="Physical directory path")
    sqlite_path: str = Field(description="Dedicated SQLite database path")
    is_isolated: bool = Field(default=True, description="Whether storage is physically isolated")


class DeleteScopeRequest(BaseModel):
    """Request to purge a physical scope partition directory."""

    coordinates: ScopeCoordinatesDTO = Field(description="Target scope coordinates to delete")


class DeleteScopeResponse(BaseModel):
    """Result of physical scope partition purge."""

    deleted: bool = Field(description="Whether the partition directory was deleted")
    namespace_hash: str = Field(description="Namespace hash of the purged scope")


class ProviderAssessRequest(BaseModel):
    """Request to assess provider availability and degradation status."""

    configured_providers: dict[str, str] = Field(
        description="Mapping of provider type (embedder, llm, vector_store) to vendor name"
    )
    strict_mode: bool = Field(
        default=False,
        description="Whether to fail strictly when an external provider degrades",
    )


class ProviderDegradedInfoDTO(BaseModel):
    """Degradation details for a specific provider type."""

    provider_type: str = Field(description="Type of provider (e.g., embedder, llm)")
    configured_vendor: str = Field(description="Vendor requested by configuration")
    active_vendor: str = Field(description="Actual active runtime vendor")
    is_degraded: bool = Field(description="Whether operating in fallback degraded mode")
    degradation_reason: str = Field(default="", description="Human-readable explanation of degradation")


class DegradedReportResponse(BaseModel):
    """Consolidated degradation diagnostic report."""

    overall_status: str = Field(description="Overall severity: healthy, degraded_lexical_fallback, etc.")
    providers: list[ProviderDegradedInfoDTO] = Field(
        default_factory=list, description="Per-provider degradation details"
    )
    strict_mode: bool = Field(description="Whether strict mode was enabled")
    summary: str = Field(description="Executive summary of memory provider status")


class FormatCliEnvelopeRequest(BaseModel):
    """Request to format execution result into machine CLI envelope."""

    command: str = Field(description="Command name executed")
    scope: ScopeCoordinatesDTO = Field(description="Scope coordinates associated with execution")
    payload: dict[str, str] = Field(default_factory=dict, description="Result payload key-values")
    agent_mode: bool = Field(default=True, description="Whether running in unattended agent mode")


class CliEnvelopeResponse(BaseModel):
    """Machine envelope representation for terminal or automation tool loops."""

    status: str = Field(description="Execution status: success or error")
    command: str = Field(description="Command name")
    duration_ms: int = Field(ge=0, description="Execution duration in milliseconds")
    scope: dict[str, str] = Field(description="Target scope coordinates map")
    payload: dict[str, str] = Field(default_factory=dict, description="Execution result payload")
    error_code: str = Field(default="", description="Structured error code if failed")
    error_message: str = Field(default="", description="Error description if failed")
    exit_code: int = Field(default=0, description="Numeric process exit code")
    auto_confirmed: bool = Field(default=True, description="Whether interactive prompts were auto-assumed")


class SurveyFindingDTO(BaseModel):
    """Findings from repository survey before memory integration."""

    message_assembly_site: str = Field(description="Source file and line where model prompt is constructed")
    identity_binding: str = Field(description="Variable or expression providing user/session identity")
    installed_provider: str = Field(description="Installed libraries or available runtime credentials")
    write_hook_seam: str = Field(description="Location where post-turn response transcript is available")
    is_ready_for_wiring: bool = Field(default=True, description="Whether repository is ready for wiring")


class ValidateSurveyRequest(BaseModel):
    """Request to validate pre-integration survey findings."""

    finding: SurveyFindingDTO = Field(description="Survey findings to validate")


class ValidateSurveyResponse(BaseModel):
    """Validation verdict for repository pre-integration survey."""

    is_valid: bool = Field(description="Whether survey answered all 4 critical questions")
    issues: list[str] = Field(default_factory=list, description="List of unaddressed architectural gaps")


class VerifySeamsRequest(BaseModel):
    """Request to verify read and write integration seams."""

    read_seam_configured: bool = Field(description="Whether memory recall injection seam is placed")
    write_seam_configured: bool = Field(description="Whether post-turn memory persistence seam is placed")
    token_budget: int = Field(default=400, gt=0, description="Injected context token budget ceiling")
    roundtrip_test_passed: bool = Field(default=True, description="Whether failing roundtrip test has passed")


class VerifySeamsResponse(BaseModel):
    """Seam configuration validation result."""

    is_verified: bool = Field(description="Whether seams are completely verified")
    message: str = Field(description="Verification diagnostics message")


class SkillTriadHealthResponse(BaseModel):
    """Operational health status for skill triad subsystem."""

    status: str = Field(default="ok")
    module: str = Field(default="skill_triad")
    version: str = Field(default="1.0.0")
