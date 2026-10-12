"""Pydantic schemas for Directory Trust Gate and Remote Memory Resolution.

[INPUT]
- None.

[OUTPUT]
- Typed DTO models for directory trust management and project memory config resolution.

[POS]
- Server schemas. Exposes typed contracts for directory trust gating and remote memory egress boundaries.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class TrustDirectoryRequest(BaseModel):
    """Request payload to add a directory to trusted boundaries."""

    model_config = ConfigDict(extra="forbid")

    directory: str = Field(..., description="Target directory path to mark as trusted")


class TrustDirectoryResponse(BaseModel):
    """Result of directory trust addition."""

    model_config = ConfigDict(extra="forbid")

    directory: str = Field(..., description="Requested directory path")
    canonical_path: str = Field(..., description="Absolute canonical resolved directory path")
    trusted: bool = Field(..., description="Whether directory is currently trusted")


class UntrustDirectoryRequest(BaseModel):
    """Request payload to remove trust from a directory."""

    model_config = ConfigDict(extra="forbid")

    directory: str = Field(..., description="Target directory path to remove from trusted roots")


class UntrustDirectoryResponse(BaseModel):
    """Result of directory trust revocation."""

    model_config = ConfigDict(extra="forbid")

    directory: str = Field(..., description="Requested directory path")
    removed: bool = Field(..., description="True if an active entry was revoked")


class ListTrustedDirectoriesResponse(BaseModel):
    """List of all canonical trusted directory boundaries."""

    model_config = ConfigDict(extra="forbid")

    trusted_directories: list[str] = Field(
        default_factory=list, description="Canonical directory paths"
    )
    count: int = Field(..., description="Total count of trusted directories")


class ProjectMemoryConfigDto(BaseModel):
    """Project-level memory and remote telemetry settings payload."""

    model_config = ConfigDict(extra="forbid")

    scope: str | None = Field(default=None, description="Local or team memory scope name")
    domain: str | None = Field(default=None, description="Domain classification tag")
    remote_url: str | None = Field(
        default=None, description="Outbound destination URL for remote memory host"
    )
    remote_token: str | None = Field(
        default=None, description="Authorization token for remote memory host"
    )
    remote_scopes: list[str] = Field(
        default_factory=list, description="Remote namespace scopes"
    )


class ResolveDirectoryTrustRequest(BaseModel):
    """Request to resolve memory configuration and evaluate directory trust gate."""

    model_config = ConfigDict(extra="forbid")

    start_directory: str = Field(
        ..., description="Execution workspace directory to evaluate"
    )
    config_override: ProjectMemoryConfigDto | None = Field(
        default=None, description="Optional explicit in-memory config override"
    )


class ResolvedDirectoryTrustDto(BaseModel):
    """Outcome of single-point directory trust resolution."""

    model_config = ConfigDict(extra="forbid")

    config_path: str | None = Field(
        default=None, description="Resolved config file path"
    )
    config_dir: str | None = Field(
        default=None, description="Directory housing memory configuration"
    )
    is_directory_trusted: bool = Field(
        ..., description="Whether directory hierarchy is trusted"
    )
    effective_scope: str | None = Field(
        default=None, description="Effective local visibility scope"
    )
    effective_domain: str | None = Field(
        default=None, description="Effective domain category"
    )
    remote_url: str | None = Field(
        default=None, description="Remote memory URL if authorized, or None if refused"
    )
    remote_token: str | None = Field(
        default=None, description="Remote memory token if authorized, or None if refused"
    )
    remote_scopes: list[str] = Field(
        default_factory=list, description="Authorized remote memory scopes"
    )
    refusal_notice: str | None = Field(
        default=None, description="Actionable security warning when untrusted remote egress dropped"
    )
    decision: str = Field(
        ...,
        description="TRUSTED_AUTHORIZED, UNTRUSTED_REMOTE_REFUSED, LOCAL_SCOPE_ONLY, or NO_CONFIG_FOUND",
    )
