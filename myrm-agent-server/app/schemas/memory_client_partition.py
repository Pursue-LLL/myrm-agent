"""
[POS] app/schemas/memory_client_partition.py
[INPUT] pydantic
[OUTPUT] ClientPartitionConfigDTO, ClientWorkspaceDescriptorDTO, ScreenClientMemoriesCandidateDTO, ScreenClientMemoriesRequestDTO, CrossClientLeakViolationDTO, ScreenClientMemoriesResponseDTO

Pydantic DTOs for Client-Isolated Workspace and Memory Namespace Partition Suite.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ClientPartitionConfigDTO(BaseModel):
    """Configuration DTO for client workspace mounting and memory scoping."""

    model_config = ConfigDict(extra="forbid")

    client_id: str = Field(..., description="Unique client identifier slug")
    client_name: str | None = Field(default=None, description="Human-readable client display name")
    workspace_root: str = Field(
        default="workspaces/clients",
        description="Base directory for client workspace mounts",
    )
    allow_global_read: bool = Field(
        default=True,
        description="Whether this client context is allowed to read shared global memories",
    )
    strict_leak_check: bool = Field(
        default=True,
        description="Whether to strictly intercept detected cross-client leakage",
    )


class ClientWorkspaceDescriptorDTO(BaseModel):
    """Metadata describing a resolved, quarantined client workspace directory."""

    model_config = ConfigDict(extra="forbid")

    client_id: str = Field(..., description="Target client identifier")
    relative_path: str = Field(..., description="Normalized relative path from sandbox root")
    absolute_path: str = Field(..., description="Canonical absolute path on file system")
    is_isolated: bool = Field(default=True, description="Whether the workspace path is safely quarantined")


class ScreenClientMemoriesCandidateDTO(BaseModel):
    """A memory candidate to screen against cross-client leakage."""

    model_config = ConfigDict(extra="forbid")

    memory_id: str = Field(..., description="Unique memory identifier")
    content: str = Field(..., description="Text content of the memory")
    primary_namespace: str = Field(..., description="Authoritative primary namespace")
    namespaces: list[str] = Field(default_factory=list, description="Derived namespace list")
    client_id: str | None = Field(default=None, description="Client ownership tag if present")
    score: float = Field(default=1.0, ge=0.0, le=1.0, description="Retrieval match score")


class ScreenClientMemoriesRequestDTO(BaseModel):
    """Request payload to screen memory retrieval candidates for a specific client session."""

    model_config = ConfigDict(extra="forbid")

    target_client_id: str = Field(..., description="Active client requesting memory recall")
    candidates: list[ScreenClientMemoriesCandidateDTO] = Field(
        default_factory=list, description="Raw memory candidates before screening"
    )
    allow_global: bool = Field(
        default=True,
        description="Whether shared global memories are permitted in results",
    )


class CrossClientLeakViolationDTO(BaseModel):
    """Forensic report entry of an intercepted cross-client leak attempt."""

    model_config = ConfigDict(extra="forbid")

    target_client_id: str = Field(..., description="Active client context")
    offending_client_id: str | None = Field(
        default=None, description="Foreign client identifier attached to memory"
    )
    offending_namespace: str = Field(..., description="Namespace causing the violation")
    memory_id: str | None = Field(default=None, description="Leaking memory ID")
    reason: str = Field(..., description="Reason for containment interception")


class ScreenClientMemoriesResponseDTO(BaseModel):
    """Result of memory screening and cross-client leakage interception."""

    model_config = ConfigDict(extra="forbid")

    target_client_id: str = Field(..., description="Active client identifier")
    total_evaluated: int = Field(default=0, ge=0, description="Total candidates evaluated")
    allowed_count: int = Field(default=0, ge=0, description="Total safe memories allowed")
    filtered_count: int = Field(default=0, ge=0, description="Total foreign memories intercepted")
    safe_memory_ids: list[str] = Field(default_factory=list, description="List of approved memory IDs")
    violations: list[CrossClientLeakViolationDTO] = Field(
        default_factory=list, description="Audit records of intercepted violations"
    )
