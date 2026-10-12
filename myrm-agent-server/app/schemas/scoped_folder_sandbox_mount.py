"""Pydantic schemas for Scoped Folder Permission Dialog and Sandbox Dynamic Mount Suite.

[POS] app/schemas/scoped_folder_sandbox_mount.py
[INPUT] pydantic
[OUTPUT] ValidatePathSecurityRequest, ValidatePathSecurityResponse, ScopedFolderGrantRequest, ScopedFolderGrantDTO, DynamicMountSpecDTO, RevokeGrantResponse
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ValidatePathSecurityRequest(BaseModel):
    """Request payload to pre-validate whether a host path violates security blacklists."""

    model_config = ConfigDict(frozen=True)

    path: str = Field(..., description="Target host filesystem directory to inspect")


class ValidatePathSecurityResponse(BaseModel):
    """Verification result detailing path validation outcome."""

    model_config = ConfigDict(frozen=True)

    is_blocked: bool
    resolved_path: str
    matched_rule: str | None = None
    reason: str | None = None


class ScopedFolderGrantRequest(BaseModel):
    """Request payload to authorize and dynamically project a host folder into sandbox."""

    model_config = ConfigDict(frozen=True)

    folder_path: str = Field(..., description="Absolute or expandable host folder path")
    access_mode: str = Field(default="READ_ONLY", description="Privilege level: READ_ONLY or READ_WRITE")
    lifecycle: str = Field(default="EPHEMERAL_PER_SESSION", description="EPHEMERAL_PER_SESSION or PERSISTENT_UNTIL_REVOKED")
    lease_seconds: float | None = Field(default=3600.0, description="Authorization duration in seconds")
    alias_slug: str | None = Field(default=None, description="Optional custom slug for mount path alias")


class ScopedFolderGrantDTO(BaseModel):
    """Data transfer object describing an authorized folder grant and mount projection."""

    model_config = ConfigDict(frozen=True)

    grant_id: str
    folder_path: str
    alias_slug: str
    access_mode: str
    lifecycle: str
    sandbox_mount_path: str
    granted_at: float
    expires_at: float | None = None
    is_revoked: bool
    revoked_at: float | None = None


class DynamicMountSpecDTO(BaseModel):
    """Container virtualization mount specification."""

    model_config = ConfigDict(frozen=True)

    source_host_path: str
    sandbox_target_path: str
    read_only: bool
    grant_id: str


class RevokeGrantResponse(BaseModel):
    """Outcome of revoking an active folder grant."""

    model_config = ConfigDict(frozen=True)

    grant_id: str
    revoked: bool
    message: str
