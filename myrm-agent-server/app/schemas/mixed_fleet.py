"""Pydantic V2 schemas for Mixed Fleet Local Brain and Remote Executor (Item 47).

[INPUT]
- DispatchHandoffRequestSchema, UpdateFleetHeartbeatRequestSchema,
  CompleteRemoteExecutionRequestSchema, FailRemoteExecutionRequestSchema.

[OUTPUT]
- FleetNodeSpecDTO, MixedFleetHandoffManifestDTO, FleetStatusSnapshotResponseDTO,
  MixedFleetPresetSpecDTO.

[POS]
- Server-side typed DTO schemas for Mixed Fleet orchestration.
"""

from __future__ import annotations

import enum
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field


class FleetRoleEnum(enum.StrEnum):
    """Roles within the mixed fleet topology."""

    LOCAL_BRAIN = "local_brain"
    REMOTE_EXECUTOR = "remote_executor"


class FleetExecutionStatusEnum(enum.StrEnum):
    """Execution status of a mixed fleet handoff manifest."""

    IDLE = "idle"
    DISPATCHED = "dispatched"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    OFFLINE = "offline"


class FleetNodeSpecDTO(BaseModel):
    """DTO representing a node in the mixed fleet."""

    model_config = ConfigDict(frozen=True)

    node_id: str = Field(..., description="Unique node identifier")
    role: FleetRoleEnum = Field(..., description="Node role in mixed fleet")
    display_name: str = Field(..., description="Human-readable node title")
    is_online: bool = Field(default=True, description="Online/reachable flag")
    endpoint_url: str | None = Field(default=None, description="Remote API endpoint if applicable")
    last_heartbeat: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat(),
        description="ISO timestamp of last heartbeat",
    )
    supported_capabilities: list[str] = Field(
        default_factory=list, description="Capabilities provided by this node"
    )


class MixedFleetHandoffManifestDTO(BaseModel):
    """DTO representing a structured handoff manifest between Local Brain and Remote Executor."""

    model_config = ConfigDict(frozen=True)

    manifest_id: str = Field(..., description="Unique handoff manifest identifier")
    chat_id: str = Field(..., description="Associated chat session identifier")
    source_role: FleetRoleEnum = Field(..., description="Originating node role")
    target_role: FleetRoleEnum = Field(..., description="Receiving node role")
    task_instruction: str = Field(..., description="Task objective instruction")
    handoff_markdown: str = Field(..., description="Structured markdown handoff contract")
    context_files: list[str] = Field(default_factory=list, description="Injected context files")
    execution_status: FleetExecutionStatusEnum = Field(
        default=FleetExecutionStatusEnum.DISPATCHED, description="Current execution state"
    )
    created_at: str = Field(..., description="Dispatch timestamp")
    synced_at: str | None = Field(default=None, description="Sync timestamp")
    output_summary: str | None = Field(default=None, description="Result output summary")
    error_detail: str | None = Field(default=None, description="Error details if failed")


class DispatchHandoffRequestSchema(BaseModel):
    """Payload to dispatch task from Local Brain to Remote Executor."""

    task_instruction: str = Field(
        ..., min_length=1, description="Task instruction for Remote Executor"
    )
    context_files: list[str] = Field(
        default_factory=list, description="List of local file paths to package"
    )


class UpdateFleetHeartbeatRequestSchema(BaseModel):
    """Payload to update node heartbeat or availability."""

    role: FleetRoleEnum = Field(..., description="Target node role")
    is_online: bool = Field(default=True, description="Online state")


class CompleteRemoteExecutionRequestSchema(BaseModel):
    """Payload to mark remote execution as completed."""

    output_summary: str = Field(
        ..., min_length=1, description="Structured result summary from Remote Executor"
    )


class FailRemoteExecutionRequestSchema(BaseModel):
    """Payload to mark remote execution as failed."""

    error_detail: str = Field(..., min_length=1, description="Diagnostic error details")


class FleetStatusSnapshotResponseDTO(BaseModel):
    """DTO representing overall fleet health and current active task."""

    model_config = ConfigDict(frozen=True)

    chat_id: str = Field(..., description="Chat session identifier")
    local_brain: FleetNodeSpecDTO = Field(..., description="Local Brain node spec")
    remote_executor: FleetNodeSpecDTO = Field(..., description="Remote Executor node spec")
    active_manifest: MixedFleetHandoffManifestDTO | None = Field(
        default=None, description="Most recent active handoff manifest"
    )
    total_handoffs: int = Field(default=0, description="Total count of handoffs in session")


class MixedFleetPresetSpecDTO(BaseModel):
    """Specification of the prebuilt Mixed Fleet Agent Profile template."""

    model_config = ConfigDict(frozen=True)

    preset_id: str = Field(..., description="Template identifier")
    name: str = Field(..., description="Human-readable title")
    description: str = Field(..., description="Template description")
    local_capabilities: list[str] = Field(..., description="Capabilities assigned to Local Brain")
    remote_capabilities: list[str] = Field(..., description="Capabilities assigned to Remote Executor")
    handoff_protocol: str = Field(..., description="Summary of markdown handoff protocol")
