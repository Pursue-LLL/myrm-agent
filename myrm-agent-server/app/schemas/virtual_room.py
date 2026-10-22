"""Pydantic V2 schemas for Multi-Human Multi-Agent Collaborative Virtual Room (Item 59).

[INPUT]
- CreateRoomRequest, JoinRoomRequest, LeaveRoomRequest, AcquireFileLockRequest,
  ReleaseFileLockRequest, CreateBorrowingGrantRequest, DelegateExecutionRequest,
  RevokeBorrowingGrantRequest, RegisterServiceRelayRequest.

[OUTPUT]
- VirtualRoomStateDTO, VirtualRoomParticipantDTO, FileBlockLeaseLockDTO,
  AgentBorrowingGrantDTO, RoomServicePortRelayDTO, VirtualRoomActivityEventDTO,
  and standardized responses.

[POS]
- Server-side DTO contracts for Tutti-style collaborative multi-human multi-agent co-dev.
"""

from __future__ import annotations

import enum

from pydantic import BaseModel, ConfigDict, Field


class ParticipantRoleDTOEnum(enum.StrEnum):
    """Role classification of room participants."""

    HUMAN_DEV = "human_dev"
    AGENT_WORKER = "agent_worker"
    AGENT_REVIEWER = "agent_reviewer"
    AGENT_ARCHITECT = "agent_architect"


class LockScopeDTOEnum(enum.StrEnum):
    """Granularity scope of a collaborative filesystem lease lock."""

    FILE_FULL = "file_full"
    LINE_RANGE = "line_range"
    AST_BLOCK = "ast_block"


class BorrowingGrantStatusDTOEnum(enum.StrEnum):
    """Lifecycle state of an agent capability borrowing grant."""

    ACTIVE = "active"
    REVOKED = "revoked"
    EXPIRED = "expired"
    EXHAUSTED = "exhausted"


class VirtualRoomParticipantDTO(BaseModel):
    """Participant (human or AI agent) co-existing in a virtual room."""

    model_config = ConfigDict(frozen=True)

    participant_id: str = Field(..., description="Unique participant identifier")
    name: str = Field(..., description="Display name")
    role: ParticipantRoleDTOEnum = Field(..., description="Participant role")
    local_identity_bound: bool = Field(True, description="Whether identity remains strictly local")
    is_active: bool = Field(True, description="Online/active status in the room")
    joined_at: float = Field(..., description="Epoch timestamp of joining")


class FileBlockLeaseLockDTO(BaseModel):
    """Active in-flight file block lease lock."""

    model_config = ConfigDict(frozen=True)

    lock_id: str = Field(..., description="Unique lock identifier")
    file_path: str = Field(..., description="Normalized target file path")
    holder_id: str = Field(..., description="Identifier of the lock holder")
    holder_role: ParticipantRoleDTOEnum = Field(..., description="Role of the lock holder")
    scope: LockScopeDTOEnum = Field(..., description="Lock granularity scope")
    start_line: int | None = Field(None, ge=1, description="Start line for range lock")
    end_line: int | None = Field(None, ge=1, description="End line for range lock")
    acquired_at: float = Field(..., description="Epoch acquisition timestamp")
    expires_at: float = Field(..., description="Epoch expiration timestamp")
    ttl_seconds: float = Field(..., ge=1.0, description="Duration in seconds")


class AgentBorrowingGrantDTO(BaseModel):
    """Zero-credential capability borrowing grant."""

    model_config = ConfigDict(frozen=True)

    grant_id: str = Field(..., description="Unique borrowing grant ID")
    room_id: str = Field(..., description="Target room ID")
    owner_id: str = Field(..., description="Grantor / capability owner participant ID")
    borrower_id: str = Field(..., description="Beneficiary / borrower participant ID")
    target_agent_model: str = Field(..., description="Borrowed model identifier (e.g. claude-3-7-sonnet)")
    quota_tokens: int = Field(..., ge=1, description="Maximum allotted token budget")
    used_tokens: int = Field(0, ge=0, description="Consumed token count")
    status: BorrowingGrantStatusDTOEnum = Field(..., description="Lifecycle status")
    expires_at: float = Field(..., description="Epoch expiration timestamp")


class RoomServicePortRelayDTO(BaseModel):
    """Sandbox live preview port relay."""

    model_config = ConfigDict(frozen=True)

    relay_id: str = Field(..., description="Unique relay identifier")
    room_id: str = Field(..., description="Target room ID")
    service_name: str = Field(..., description="Name of the service (e.g. web-frontend)")
    port: int = Field(..., ge=1, le=65535, description="Internal service port")
    live_preview_url: str = Field(..., description="Room-wide accessible preview URL")
    launched_by_id: str = Field(..., description="Identifier of participant who launched service")
    is_healthy: bool = Field(True, description="Service health indicator")
    created_at: float = Field(..., description="Epoch creation timestamp")


class VirtualRoomActivityEventDTO(BaseModel):
    """Audit event in persistent room memory."""

    model_config = ConfigDict(frozen=True)

    event_id: str = Field(..., description="Unique event identifier")
    room_id: str = Field(..., description="Associated room ID")
    actor_id: str = Field(..., description="Participant who triggered the event")
    event_type: str = Field(..., description="Type category of collaborative event")
    details: dict[str, str | int | float | bool] = Field(
        default_factory=dict, description="Metadata details"
    )
    timestamp: float = Field(..., description="Epoch event timestamp")


class VirtualRoomStateDTO(BaseModel):
    """Current unified snapshot state of a collaborative room."""

    model_config = ConfigDict(frozen=True)

    room_id: str = Field(..., description="Unique room identifier")
    name: str = Field(..., description="Human-readable room title")
    participants: list[VirtualRoomParticipantDTO] = Field(default_factory=list)
    active_locks: list[FileBlockLeaseLockDTO] = Field(default_factory=list)
    borrowing_grants: list[AgentBorrowingGrantDTO] = Field(default_factory=list)
    service_relays: list[RoomServicePortRelayDTO] = Field(default_factory=list)
    created_at: float = Field(..., description="Room creation epoch timestamp")
    last_activity_at: float = Field(..., description="Most recent collaborative activity timestamp")


class CreateRoomRequest(BaseModel):
    """Request payload to create a new collaborative virtual room."""

    room_id: str = Field(..., min_length=1, description="Unique room identifier")
    name: str = Field(..., min_length=1, description="Human-readable workspace title")


class JoinRoomRequest(BaseModel):
    """Request payload to join a collaborative virtual room."""

    participant_id: str = Field(..., min_length=1, description="Unique participant identifier")
    name: str = Field(..., min_length=1, description="Display name")
    role: ParticipantRoleDTOEnum = Field(..., description="Role classification")
    local_identity_bound: bool = Field(True, description="Strict local credential binding flag")


class LeaveRoomRequest(BaseModel):
    """Request payload to leave a collaborative room."""

    participant_id: str = Field(..., min_length=1, description="Leaving participant ID")


class AcquireFileLockRequest(BaseModel):
    """Request payload to acquire an in-flight file or line-range lease lock."""

    file_path: str = Field(..., min_length=1, description="Target relative file path")
    holder_id: str = Field(..., min_length=1, description="Lock holder participant ID")
    holder_role: ParticipantRoleDTOEnum = Field(..., description="Role of holder")
    scope: LockScopeDTOEnum = Field(default=LockScopeDTOEnum.FILE_FULL, description="Lock granularity")
    start_line: int | None = Field(None, ge=1, description="Start line for range lock")
    end_line: int | None = Field(None, ge=1, description="End line for range lock")
    ttl_seconds: float = Field(15.0, ge=1.0, le=120.0, description="Lease duration in seconds")


class ReleaseFileLockRequest(BaseModel):
    """Request payload to release an active file lock."""

    lock_id: str = Field(..., min_length=1, description="Target lock ID")
    holder_id: str = Field(..., min_length=1, description="Current holder participant ID")


class CreateBorrowingGrantRequest(BaseModel):
    """Request payload to issue a zero-credential agent capability borrowing grant."""

    room_id: str = Field(..., min_length=1, description="Associated virtual room ID")
    owner_id: str = Field(..., min_length=1, description="Grantor participant ID")
    borrower_id: str = Field(..., min_length=1, description="Borrower participant ID")
    target_agent_model: str = Field(..., min_length=1, description="Model to delegate (e.g. claude-3-7-sonnet)")
    quota_tokens: int = Field(..., ge=1, description="Allotted token budget")
    ttl_seconds: float = Field(3600.0, ge=60.0, le=86400.0, description="Grant validity in seconds")


class DelegateExecutionRequest(BaseModel):
    """Request payload to execute an Agent task via a borrowed grant."""

    grant_id: str = Field(..., min_length=1, description="Borrowing grant ID")
    borrower_id: str = Field(..., min_length=1, description="Borrower participant ID")
    prompt: str = Field(..., min_length=1, description="Task prompt to execute")
    token_cost: int = Field(150, ge=1, description="Estimated/metered token consumption")


class RevokeBorrowingGrantRequest(BaseModel):
    """Request payload to immediately revoke an agent capability grant."""

    grant_id: str = Field(..., min_length=1, description="Target grant ID")
    owner_id: str = Field(..., min_length=1, description="Grant owner participant ID")


class RegisterServiceRelayRequest(BaseModel):
    """Request payload to publish a live preview port relay across the room."""

    room_id: str = Field(..., min_length=1, description="Target room ID")
    service_name: str = Field(..., min_length=1, description="Human-readable service title")
    port: int = Field(..., ge=1, le=65535, description="Internal container/host service port")
    launched_by_id: str = Field(..., min_length=1, description="Participant ID who launched the service")
