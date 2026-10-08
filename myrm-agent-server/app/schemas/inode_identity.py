"""Pydantic V2 schemas for directory inode identity resolution and sync guard API.

[POS]
Data transfer objects and request/response models for filesystem inode identity,
directory rename/move detection, and cross-volume double-sync prevention.

[INPUT]
- pydantic::BaseModel, Field

[OUTPUT]
- DirectoryIdentityDTO
- ResolveIdentityRequest
- ResolveIdentityResponse
- KnownIdentityDTO
- VerifySyncRequest
- VerifySyncResponse
- InodeIdentityHealthResponse
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class DirectoryIdentityDTO(BaseModel):
    """Data transfer object for physical directory identity."""

    canonical_path: str = Field(description="Canonical absolute path on host filesystem")
    device_id: int = Field(description="Device or volume identifier (st_dev)")
    inode_id: int = Field(description="Inode or file index identifier (st_ino)")
    birth_time_ns: int = Field(description="Creation or metadata change time in nanoseconds")
    root_signature: str = Field(description="Lightweight root identity fingerprint")
    fs_kind: str = Field(default="posix", description="Host filesystem environment type")
    is_symlink: bool = Field(default=False, description="Whether the original path was a symlink")
    physical_key: str = Field(description="Composite physical primary key 'device_id:inode_id'")


class ResolveIdentityRequest(BaseModel):
    """Request model for probing directory physical identity."""

    target_path: str = Field(min_length=1, description="Filesystem directory path to evaluate")


class ResolveIdentityResponse(BaseModel):
    """Response model for directory physical identity resolution."""

    target_path: str = Field(description="Original requested path")
    real_path: str = Field(description="Real absolute path resolved following symlinks")
    is_accessible: bool = Field(description="Whether the path exists and is accessible")
    is_directory: bool = Field(description="Whether the resolved target is a directory")
    is_symlink: bool = Field(default=False, description="Whether the requested path is a symlink")
    identity: DirectoryIdentityDTO | None = Field(default=None, description="Resolved physical identity")
    error_message: str | None = Field(default=None, description="Error detail if inaccessible")


class KnownIdentityDTO(BaseModel):
    """Previously registered directory identity for comparison."""

    canonical_path: str = Field(description="Previously recorded canonical path")
    device_id: int = Field(description="Recorded device ID")
    inode_id: int = Field(description="Recorded inode ID")
    birth_time_ns: int = Field(default=0, description="Recorded creation timestamp in ns")
    root_signature: str = Field(default="", description="Recorded root fingerprint")
    fs_kind: str = Field(default="posix", description="Filesystem type")


class VerifySyncRequest(BaseModel):
    """Request to verify and arbitrate workspace directory identity before sync."""

    target_path: str = Field(min_length=1, description="Current workspace directory to sync")
    known_identities: list[KnownIdentityDTO] = Field(
        default_factory=list,
        description="List of previously registered directory identities",
    )


class VerifySyncResponse(BaseModel):
    """Directive result emitted by sync identity arbitrator."""

    action: str = Field(
        description="Directive action: proceed_incremental, relocate_and_proceed, rebuild_warning, register_new, blocked"
    )
    match_kind: str = Field(
        description="Match classification: exact_match, moved_or_renamed, inode_reused, brand_new"
    )
    reason: str = Field(description="Human-readable explanation of arbitration verdict")
    old_path: str | None = Field(default=None, description="Previous recorded path if moved or renamed")
    new_path: str = Field(description="Current canonical path of the workspace")
    physical_key: str = Field(description="Current physical identity composite key")
    needs_database_relocation: bool = Field(
        default=False,
        description="Whether existing DB workspace pointers must be relocated",
    )
    identity: DirectoryIdentityDTO | None = Field(default=None, description="Current directory identity")


class InodeIdentityHealthResponse(BaseModel):
    """Health check response for the inode identity subsystem."""

    status: str = Field(default="ok")
    module: str = Field(default="inode_identity")
    version: str = Field(default="1.0.0")
