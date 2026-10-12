"""Pydantic schemas for Directory Trust Gate and Remote Memory Resolution.

[INPUT]
- None.

[OUTPUT]
- Typed DTO models for directory trust registration, status checks, and project memory resolution.

[POS]
- Server schemas. Exposes typed contracts separating local scope filtering from remote memory egress.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class TrustDirectoryRequest(BaseModel):
    """Request payload to add or remove a directory from the trusted registry."""

    model_config = ConfigDict(extra="forbid")

    directory: str = Field(..., description="Filesystem directory path to trust or untrust")
    action: Literal["trust", "untrust"] = Field(
        default="trust", description="Action to perform: 'trust' or 'untrust'"
    )


class TrustDirectoryResponse(BaseModel):
    """Outcome of trusting or untrusting a workspace directory."""

    model_config = ConfigDict(extra="forbid")

    directory: str = Field(..., description="Original requested directory path")
    canonical_path: str = Field(..., description="Canonical resolved absolute path")
    is_trusted: bool = Field(..., description="Current trust status of the directory")
    action: str = Field(..., description="Action that was executed ('trust' or 'untrust')")


class CheckDirectoryTrustResponse(BaseModel):
    """Result of querying a directory's trust status."""

    model_config = ConfigDict(extra="forbid")

    directory: str = Field(..., description="Requested directory path")
    canonical_path: str = Field(..., description="Canonical resolved path")
    is_trusted: bool = Field(..., description="True if path is within a trusted root")


class ProjectMemoryConfigDto(BaseModel):
    """Project-level memory configuration declared in manifest."""

    model_config = ConfigDict(extra="forbid")

    local_scope: str | None = Field(
        default=None, description="Local recall/write scope filter (e.g. repo:my-org/project)"
    )
    domain: str | None = Field(
        default=None, description="Domain tag for memory classification"
    )
    remote_url: str | None = Field(
        default=None, description="Target remote enterprise memory server endpoint"
    )
    remote_token: str | None = Field(
        default=None, description="Authentication token for remote memory server"
    )
    remote_scopes: list[str] = Field(
        default_factory=list, description="Target remote scopes to synchronize"
    )


class ResolveProjectRemoteRequest(BaseModel):
    """Payload to atomically resolve project memory settings against directory trust gates."""

    model_config = ConfigDict(extra="forbid")

    config: ProjectMemoryConfigDto = Field(
        ..., description="Declared memory configuration from manifest"
    )
    config_path: str | None = Field(
        default=None, description="Absolute or relative path to manifest file (e.g. /repo/.myrm.yaml)"
    )


class ResolveProjectRemoteResponse(BaseModel):
    """Result of single-point directory trust resolution."""

    model_config = ConfigDict(extra="forbid")

    config_path: str | None = Field(
        default=None, description="Provided path to config file"
    )
    config_dir: str | None = Field(
        default=None, description="Resolved directory containing config file"
    )
    trust_status: str = Field(
        ..., description="TRUSTED, UNTRUSTED, or ERROR_FAIL_CLOSED"
    )
    is_trusted: bool = Field(
        ..., description="Whether directory is authorized as trusted"
    )
    remote_url: str | None = Field(
        default=None, description="Authorized remote memory server URL if permitted"
    )
    remote_token: str | None = Field(
        default=None, description="Authorized remote memory token if permitted"
    )
    remote_scopes: list[str] = Field(
        default_factory=list, description="Authorized remote scopes if permitted"
    )
    refused_from: str | None = Field(
        default=None, description="Directory path from which remote settings were refused"
    )
    refusal_notice: str | None = Field(
        default=None, description="Standardized user notification when remote memory is refused"
    )
    effective_scope: str | None = Field(
        default=None, description="Local memory scope applied for filtering"
    )
    is_outbound_authorized: bool = Field(
        ..., description="True if outbound network memory calls are authorized"
    )
