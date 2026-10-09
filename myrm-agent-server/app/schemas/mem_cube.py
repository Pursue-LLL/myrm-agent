"""[INPUT]
None (external API payload models and types for MemOS Memory Cube scoped isolation).

[OUTPUT]
MemoryCubeDTO, MountPolicyDTO, CubeQueryRequestDTO, CubeQueryResultDTO, CubeWriteRequestDTO, etc.

[POS]
Domain schemas for Item 124 Memory Cube Scoped Isolation & Dynamic Mounting suite.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class CubeScopeTypeEnum(StrEnum):
    """Scope boundaries for memory cubes."""

    GLOBAL_SHARED = "global_shared"
    PROJECT_WORKSPACE = "project_workspace"
    AGENT_PRIVATE = "agent_private"
    EPHEMERAL_TASK = "ephemeral_task"


class CubeRecordDTO(BaseModel):
    """Individual record residing in a memory cube."""

    record_id: str = Field(..., description="Unique record identifier.")
    cube_id: str = Field(..., description="Cube ID containing this record.")
    content: str = Field(..., description="Text payload of the memory.")
    metadata: dict[str, str | int | float | bool] = Field(
        default_factory=dict, description="Metadata tags attached to the record."
    )
    created_at: float = Field(..., description="Unix timestamp of record creation.")


class MemoryCubeDTO(BaseModel):
    """Compartment container for isolated memories."""

    cube_id: str = Field(..., description="Unique identifier of the memory cube.")
    name: str = Field(..., description="Human-readable title.")
    scope_type: CubeScopeTypeEnum = Field(..., description="Scope boundary type.")
    owner_id: str | None = Field(None, description="Identifier of the cube owner.")
    description: str = Field("", description="Purpose and description of the cube.")
    is_read_only: bool = Field(False, description="Whether direct write operations are forbidden.")
    item_count: int = Field(0, description="Number of memory records held.")
    created_at: float = Field(..., description="Creation epoch timestamp.")
    updated_at: float = Field(..., description="Last update epoch timestamp.")


class CreateCubeRequestDTO(BaseModel):
    """Payload to provision a new memory cube."""

    cube_id: str | None = Field(None, description="Optional custom cube ID.")
    name: str = Field(..., description="Name for the memory cube.")
    scope_type: CubeScopeTypeEnum = Field(..., description="Boundary scope type.")
    owner_id: str | None = Field(None, description="Owner identifier.")
    description: str = Field("", description="Cube description.")
    is_read_only: bool = Field(False, description="Set as immutable/read-only.")


class MountPolicyDTO(BaseModel):
    """Mount policy mapping read/write permissions for an agent."""

    agent_id: str = Field(..., description="Agent identifier.")
    readable_cube_ids: list[str] = Field(default_factory=list, description="Cubes readable by this agent.")
    writable_cube_ids: list[str] = Field(default_factory=list, description="Cubes writable by this agent.")
    default_write_cube_id: str | None = Field(None, description="Target cube for writes when unspecified.")
    strict_isolation: bool = Field(True, description="Strictly block writes to non-writable cubes.")


class SetMountPolicyRequestDTO(BaseModel):
    """Update mount policy for an agent."""

    readable_cube_ids: list[str] = Field(..., description="Permitted readable cube IDs.")
    writable_cube_ids: list[str] = Field(..., description="Permitted writable cube IDs.")
    default_write_cube_id: str | None = Field(None, description="Default write destination cube.")
    strict_isolation: bool = Field(True, description="Enforce strict isolation.")


class CubeQueryRequestDTO(BaseModel):
    """Federated search across readable cubes."""

    agent_id: str = Field(..., description="Agent issuing the query.")
    query: str = Field(..., description="Search keyword or semantic query string.")
    explicit_cube_ids: list[str] | None = Field(None, description="Optional explicit cube subset filter.")
    limit: int = Field(10, description="Max results returned.")


class CubeQueryResultDTO(BaseModel):
    """Federated query results."""

    items: list[CubeRecordDTO] = Field(default_factory=list, description="Retrieved memory records.")
    total_found: int = Field(0, description="Total matching records count.")
    queried_cube_ids: list[str] = Field(default_factory=list, description="Cubes actually searched.")
    query_duration_ms: float = Field(0.0, description="Execution time in milliseconds.")


class CubeWriteRequestDTO(BaseModel):
    """Write memory record through mount policy router."""

    agent_id: str = Field(..., description="Author agent ID.")
    content: str = Field(..., description="Memory record content.")
    target_cube_id: str | None = Field(None, description="Explicit target cube (defaults to policy default).")
    metadata: dict[str, str | int | float | bool] = Field(
        default_factory=dict, description="Metadata tags."
    )


class CubeWriteResultDTO(BaseModel):
    """Outcome of a cube write operation."""

    success: bool = Field(..., description="Whether the record was stored.")
    record: CubeRecordDTO | None = Field(None, description="Stored record if successful.")
    destination_cube_id: str | None = Field(None, description="Cube where record was stored.")
    rejection_reason: str | None = Field(None, description="Error reason if write was blocked.")


class CubeMatrixOverviewDTO(BaseModel):
    """Global system status for memory cube topology."""

    cubes: list[MemoryCubeDTO] = Field(default_factory=list, description="All registered memory cubes.")
    policies: list[MountPolicyDTO] = Field(default_factory=list, description="Active agent mount policies.")
    total_cubes: int = Field(0, description="Total active cubes.")
    total_records: int = Field(0, description="Total records across all cubes.")
    system_healthy: bool = Field(True, description="Health status of cube isolation.")
