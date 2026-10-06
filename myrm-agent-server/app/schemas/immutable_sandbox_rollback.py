"""Pydantic schemas for Immutable Host Containerized Sandbox and Rollback API.

[POS] app/schemas/immutable_sandbox_rollback.py
[INPUT] pydantic
[OUTPUT] EvaluateCommandBlastRadiusRequest, EvaluateCommandBlastRadiusResponse, CreateCheckpointRequest, CheckpointResponse, RollbackRequest, RollbackResponse, ListCheckpointsResponse, GetMountSpecRequest, GetMountSpecResponse
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class EvaluateCommandBlastRadiusRequest(BaseModel):
    """Request payload to evaluate prospective shell execution blast radius."""

    model_config = ConfigDict(frozen=True)

    command: str = Field(..., description="Prospective shell command to assess")


class EvaluateCommandBlastRadiusResponse(BaseModel):
    """Assessment of prospective shell execution blast radius."""

    model_config = ConfigDict(frozen=True)

    command: str
    tier: str
    blocked: bool
    targeted_immutable_paths: list[str]
    mitigation_applied: str


class GetMountSpecRequest(BaseModel):
    """Request payload to generate hardened container mount specification."""

    model_config = ConfigDict(frozen=True)

    workspace_path: str = Field(default="/workspace", description="Path within container for writable workspace")


class GetMountSpecResponse(BaseModel):
    """Container mount specification and generated runtime CLI flags."""

    model_config = ConfigDict(frozen=True)

    read_only_root: bool
    read_only_bind_mounts: list[str]
    writable_workspace_path: str
    tmpfs_mounts: list[str]
    drop_all_capabilities: bool
    docker_flags: list[str]


class CreateCheckpointRequest(BaseModel):
    """Request payload to create an atomic environment snapshot."""

    model_config = ConfigDict(frozen=True)

    sandbox_id: str = Field(..., description="Target sandbox identifier")
    description: str = Field(..., description="Human-readable description of snapshot context")
    file_manifest: dict[str, str] = Field(
        ...,
        description="Current workspace files mapping: relative_path -> sha256_hash",
    )


class CheckpointResponse(BaseModel):
    """Atomic snapshot metadata."""

    model_config = ConfigDict(frozen=True)

    checkpoint_id: str
    sandbox_id: str
    created_at: float
    description: str
    workspace_state_digest: str
    files_count: int


class RollbackRequest(BaseModel):
    """Request payload to perform zero-blast-radius environment rollback."""

    model_config = ConfigDict(frozen=True)

    sandbox_id: str
    checkpoint_id: str
    current_file_manifest: dict[str, str] = Field(
        ...,
        description="Current workspace files mapping prior to rollback",
    )


class RollbackResponse(BaseModel):
    """Outcome of atomic environment rollback."""

    model_config = ConfigDict(frozen=True)

    success: bool
    checkpoint_id: str
    restored_files_count: int
    pruned_files_count: int
    restored_at: float
    restored_manifest: dict[str, str]
    error_message: str | None = None


class ListCheckpointsResponse(BaseModel):
    """List of registered checkpoints for a sandbox."""

    model_config = ConfigDict(frozen=True)

    sandbox_id: str
    checkpoints: list[CheckpointResponse]
