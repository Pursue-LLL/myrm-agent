"""Pydantic schemas for Untrusted Project Config Isolation and Preflight Diagnostic Gate API.

[INPUT]
- Pydantic BaseModel and Field from pydantic.

[OUTPUT]
- DTO schemas for effective configuration, diagnostic results, and workspace trust status.

[POS]
Schema definitions for untrusted configuration isolation and diagnostics.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class EffectiveConfigResponse(BaseModel):
    """Effective resolved configuration payload."""

    version: str = Field(..., description="Configuration schema version")
    model_tier: str = Field(..., description="Model tier name")
    execution_timeout: float = Field(..., description="Execution timeout in seconds")
    allow_network: bool = Field(..., description="Whether outbound networking is permitted")
    cache_write_read_ratio: float = Field(..., description="Cache write/read ratio")
    sandbox_enabled: bool = Field(..., description="Whether sandbox isolation is enabled")
    anti_exfiltration_guard: bool = Field(..., description="Whether anti-exfiltration guard is enabled")
    audit_logging: bool = Field(..., description="Whether audit logging is enabled")
    custom_rules: list[str] = Field(default_factory=list, description="Custom security rule names")
    description: str = Field(default="", description="Config description")


class DiagnosticResultResponse(BaseModel):
    """Outcome of static preflight configuration diagnostics."""

    is_valid: bool = Field(..., description="Whether configuration passed all preflight checks")
    version: str = Field(..., description="Validated schema version")
    applied_tier: str = Field(..., description="Source tier applied (trusted, global, default, or untrusted_rejected)")
    unknown_keys: list[str] = Field(default_factory=list, description="Forbidden unknown keys detected")
    validation_errors: list[str] = Field(default_factory=list, description="Validation failure details")
    effective_config: EffectiveConfigResponse = Field(..., description="Effective configuration object")
    all_mandatory_features_enabled: bool = Field(..., description="Whether all mandatory security features are active")


class ResolveConfigRequest(BaseModel):
    """Request to resolve configuration for a workspace, enforcing project trust boundaries."""

    workspace_path: str = Field(..., description="Target workspace directory")
    is_project_trusted: bool = Field(default=False, description="Whether user explicitly trusted the workspace")
    global_config_path: str | None = Field(default=None, description="Optional override path for global config")


class PreflightValidateRequest(BaseModel):
    """Request to perform static preflight schema diagnostics on raw config."""

    raw_json: str | None = Field(default=None, description="Raw JSON text to parse and validate")
    config_dict: dict[str, object] | None = Field(default=None, description="Direct config dictionary to validate")
    require_all_enabled: bool = Field(default=False, description="Enforce mandatory security features enabled")


class TrustWorkspaceRequest(BaseModel):
    """Request to update trust status for a project workspace."""

    workspace_path: str = Field(..., description="Canonical path to workspace")
    trusted: bool = Field(..., description="Set true to trust, false to isolate")


class TrustWorkspaceResponse(BaseModel):
    """Trust status response for a workspace."""

    workspace_path: str = Field(..., description="Canonical path to workspace")
    is_trusted: bool = Field(..., description="Whether workspace is currently trusted")
