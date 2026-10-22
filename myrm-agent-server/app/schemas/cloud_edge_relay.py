"""Pydantic V2 schemas for Hybrid Cloud-Edge Sandbox Relay & Artifact Sync (Item 58).

[INPUT]
- RegisterArtifactRequest, AppendArtifactChunkRequest, DispatchLocalEgressRelayRequest,
  CompleteLocalEgressRelayRequest.

[OUTPUT]
- HybridArtifactStateDTO, ArtifactSyncChunkDTO, RegisterArtifactResponse,
  AppendArtifactChunkResponse, GetArtifactContentResponse, DispatchLocalEgressRelayResponse,
  CompleteLocalEgressRelayResponse, ListHybridArtifactsResponse.

[POS]
- Server-side strongly-typed DTO schemas for cross-sandbox append-only artifact synchronization
  and SSRF-safe local network egress relay execution.
"""

from __future__ import annotations

import enum

from pydantic import BaseModel, ConfigDict, Field


class ArtifactSyncModeDTOEnum(enum.StrEnum):
    """Synchronization strategy for hybrid artifacts."""

    APPEND_ONLY = "append_only"
    PATCH_DIFF = "patch_diff"
    OVERWRITE_STRICT = "overwrite_strict"


class RelayNodeRoleDTOEnum(enum.StrEnum):
    """Deployment role of the participating sandbox execution node."""

    LOCAL_SANDBOX = "local_sandbox"
    CLOUD_SANDBOX = "cloud_sandbox"
    EDGE_GATEWAY = "edge_gateway"


class NetworkEgressStatusDTOEnum(enum.StrEnum):
    """Lifecycle status of network partition egress fetch relay."""

    DIRECT_OK = "direct_ok"
    RELAY_REQUESTED = "relay_requested"
    RELAY_COMPLETED = "relay_completed"
    RELAY_FAILED = "relay_failed"


class ArtifactSyncChunkDTO(BaseModel):
    """Atomic delta chunk appended to a shared hybrid artifact."""

    model_config = ConfigDict(frozen=True)

    chunk_id: str = Field(..., description="Unique chunk delta identifier")
    artifact_id: str = Field(..., description="Target artifact identifier")
    version: int = Field(..., ge=1, description="Sequential artifact version after append")
    author_role: RelayNodeRoleDTOEnum = Field(..., description="Role of the appending sandbox node")
    content_delta: str = Field(..., description="Appended text payload")
    row_count: int = Field(..., ge=0, description="Number of rows in this delta")
    timestamp: float = Field(..., description="Epoch timestamp of chunk creation")
    checksum: str = Field(..., description="Hex SHA-256 prefix checksum of chunk payload")


class HybridArtifactStateDTO(BaseModel):
    """Current state snapshot of a hybrid synchronized artifact."""

    model_config = ConfigDict(frozen=True)

    artifact_id: str = Field(..., description="Unique artifact identifier")
    name: str = Field(..., description="Human-readable artifact title")
    current_version: int = Field(..., ge=0, description="Highest monotonic version")
    total_rows: int = Field(..., ge=0, description="Cumulative rows across all chunks")
    chunks: list[ArtifactSyncChunkDTO] = Field(
        default_factory=list, description="Chronological chunk delta chain"
    )
    last_synced_at: float = Field(0.0, description="Epoch timestamp of most recent sync")
    is_divergent: bool = Field(False, description="Flag indicating unresolved branching")


class RegisterArtifactRequest(BaseModel):
    """Request payload to initialize a shared hybrid artifact."""

    session_id: str = Field(..., min_length=1, description="Associated agent session ID")
    artifact_id: str = Field(..., min_length=1, description="Target artifact identifier")
    name: str = Field(..., min_length=1, description="Human-readable title for the artifact")
    initial_content: str = Field("", description="Optional initial baseline text content")
    initial_rows: int = Field(0, ge=0, description="Initial row count if pre-calculated")
    author_role: RelayNodeRoleDTOEnum = Field(
        default=RelayNodeRoleDTOEnum.LOCAL_SANDBOX,
        description="Author sandbox role creating the artifact",
    )


class RegisterArtifactResponse(BaseModel):
    """Response payload returned upon registering a hybrid artifact."""

    success: bool = Field(..., description="Whether registration succeeded")
    state: HybridArtifactStateDTO = Field(..., description="Registered artifact state")
    message: str = Field("", description="Informational message or error detail")


class AppendArtifactChunkRequest(BaseModel):
    """Request payload to append a chunk to a shared artifact."""

    session_id: str = Field(..., min_length=1, description="Associated agent session ID")
    artifact_id: str = Field(..., min_length=1, description="Target artifact identifier")
    content_delta: str = Field(..., min_length=1, description="Incremental content to append")
    author_role: RelayNodeRoleDTOEnum = Field(
        ..., description="Sandbox role executing the append operation"
    )
    expected_version: int | None = Field(
        None, ge=0, description="Optional CAS expected current version before append"
    )
    row_count: int | None = Field(
        None, ge=0, description="Optional explicit row count of this delta"
    )


class AppendArtifactChunkResponse(BaseModel):
    """Response payload returned upon appending an artifact chunk."""

    success: bool = Field(..., description="Whether append operation succeeded")
    state: HybridArtifactStateDTO = Field(..., description="Updated artifact state")
    message: str = Field("", description="Outcome description or conflict message")


class GetArtifactContentResponse(BaseModel):
    """Response payload containing aggregated artifact content."""

    artifact_id: str = Field(..., description="Artifact identifier")
    name: str = Field(..., description="Artifact name")
    current_version: int = Field(..., ge=0, description="Current artifact version")
    total_rows: int = Field(..., ge=0, description="Cumulative row count")
    aggregated_content: str = Field(..., description="Full reconstructed text across all chunks")


class DispatchLocalEgressRelayRequest(BaseModel):
    """Request to dispatch an outbound HTTP fetch via local network egress."""

    session_id: str = Field(..., min_length=1, description="Associated session ID")
    relay_id: str | None = Field(None, description="Optional caller-supplied relay task ID")
    target_url: str = Field(..., min_length=1, description="Target outbound URL to fetch")
    intent: str = Field(..., min_length=1, description="Reason / purpose of relay fetch")
    headers: dict[str, str] = Field(default_factory=dict, description="Outbound HTTP headers")
    payload: dict[str, str | int | float | bool] = Field(
        default_factory=dict, description="Outbound request payload params"
    )
    timeout_seconds: float = Field(15.0, gt=0.0, le=60.0, description="Fetch timeout ceiling")
    source_node: RelayNodeRoleDTOEnum = Field(
        default=RelayNodeRoleDTOEnum.CLOUD_SANDBOX,
        description="Initiating sandbox node requesting relay",
    )


class DispatchLocalEgressRelayResponse(BaseModel):
    """Response payload returned after executing or queueing local egress relay."""

    relay_id: str = Field(..., description="Unique relay transaction ID")
    status: NetworkEgressStatusDTOEnum = Field(..., description="Egress relay status")
    extracted_data: str = Field("", description="Sanitized extracted content")
    status_code: int = Field(..., description="HTTP status code from target or gateway")
    latency_ms: float = Field(..., ge=0.0, description="Observed roundtrip latency")
    error_message: str = Field("", description="Error message if fetch failed")


class CompleteLocalEgressRelayRequest(BaseModel):
    """Request to report completion of an externally executed egress relay task."""

    session_id: str = Field(..., min_length=1, description="Associated session ID")
    relay_id: str = Field(..., min_length=1, description="Target relay transaction ID")
    status_code: int = Field(..., description="Resulting HTTP status code")
    extracted_data: str = Field("", description="Extracted text or HTML payload")
    latency_ms: float = Field(0.0, ge=0.0, description="Observed roundtrip latency in ms")
    error_message: str = Field("", description="Error explanation if unsuccessful")


class CompleteLocalEgressRelayResponse(BaseModel):
    """Response returned upon saving relay execution outcome."""

    relay_id: str = Field(..., description="Relay transaction ID")
    status: NetworkEgressStatusDTOEnum = Field(..., description="Final egress status")
    success: bool = Field(..., description="Whether recording succeeded")


class ListHybridArtifactsResponse(BaseModel):
    """Response returning all tracked hybrid artifacts."""

    artifacts: list[HybridArtifactStateDTO] = Field(
        default_factory=list, description="Collection of synchronized artifacts"
    )
    total_count: int = Field(..., ge=0, description="Total number of tracked artifacts")
