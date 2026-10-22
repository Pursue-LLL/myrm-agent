"""Pydantic V2 schemas for Durable Agent Teams (Item 28).

[INPUT]
- None (root DTOs)

[OUTPUT]
- SpawnTeammateRequest, FailTeammateRequest, TeamMemberResponse
- CreateTeamTaskRequest, UpdateTeamTaskRequest, ClaimTeamTaskRequest, CompleteTeamTaskRequest, TeamTaskResponse
- SendTeamMessageRequest, DrainInboxResponse, TeamMessageResponse
- TeamProjectionResponse

[POS]
Defines API request and response contracts for durable multi-agent teams,
CAS shared task boards, and peer message communication.
"""

from __future__ import annotations

import enum

from pydantic import BaseModel, ConfigDict, Field


class TeamMemberPhaseEnum(enum.StrEnum):
    """Lifecycle phase of a durable team member."""

    PROVISIONING = "provisioning"
    ACTIVE = "active"
    FAILED = "failed"


class TeamMemberRoleEnum(enum.StrEnum):
    """Role within the team."""

    LEAD = "lead"
    TEAMMATE = "teammate"


class TeamTaskStatusEnum(enum.StrEnum):
    """Status of a task on the shared task board."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    DELETED = "deleted"


class DeliveryModeEnum(enum.StrEnum):
    """Peer mailbox delivery mode."""

    QUIET = "quiet"
    WAKING = "waking"


# -----------------------------------------------------------------------------
# Member DTOs
# -----------------------------------------------------------------------------

class SpawnTeammateRequest(BaseModel):
    """Request to spawn and register a named teammate."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., description="Unique kebab-case name of the teammate (e.g. 'researcher-alpha')")
    description: str = Field(..., description="Role and responsibility description")
    provider: str = Field(default="default", description="Model provider or execution host")
    context: str = Field(default="fresh", description="Context inheritance mode ('fresh' or 'fork')")


class FailTeammateRequest(BaseModel):
    """Request to mark a teammate as failed."""

    model_config = ConfigDict(extra="forbid")

    error: str = Field(..., description="Detailed failure diagnosis reason")


class TeamMemberResponse(BaseModel):
    """Durable team member snapshot view."""

    model_config = ConfigDict(extra="ignore")

    id: str
    name: str
    description: str
    provider: str
    context: str
    role: TeamMemberRoleEnum
    phase: TeamMemberPhaseEnum
    error: str | None = None
    created_at: float


# -----------------------------------------------------------------------------
# Task Board DTOs
# -----------------------------------------------------------------------------

class CreateTeamTaskRequest(BaseModel):
    """Request to create an unowned pending task on the shared board."""

    model_config = ConfigDict(extra="forbid")

    subject: str = Field(..., description="Task title or goal summary")
    description: str = Field(default="", description="Detailed execution instructions")
    blocked_by: list[str] = Field(default_factory=list, description="IDs of prerequisite blocker tasks")
    write_scopes: list[str] = Field(default_factory=list, description="Advisory target file or path scopes")
    owner_name: str | None = Field(default=None, description="Optional initial owner teammate name")


class UpdateTeamTaskRequest(BaseModel):
    """Request to update a task guarded by CAS expectedRevision."""

    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(..., description="Monotonically increasing CAS revision number")
    subject: str | None = Field(default=None, description="Updated task subject")
    description: str | None = Field(default=None, description="Updated task description")
    status: TeamTaskStatusEnum | None = Field(default=None, description="Updated status")
    owner_name: str | None = Field(default=None, description="Updated owner teammate name")
    blocked_by: list[str] | None = Field(default=None, description="Updated blocker task IDs")
    write_scopes: list[str] | None = Field(default=None, description="Updated write scopes")


class ClaimTeamTaskRequest(BaseModel):
    """Request to claim an unowned, ready task."""

    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(..., description="Current CAS revision number before claim")
    owner_name: str = Field(..., description="Claimant teammate name")


class CompleteTeamTaskRequest(BaseModel):
    """Request to mark a task as completed."""

    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(..., description="Current CAS revision number before completion")


class TeamTaskResponse(BaseModel):
    """Runtime-enriched task view on the shared board."""

    model_config = ConfigDict(extra="ignore")

    id: str
    revision: int
    subject: str
    description: str
    status: TeamTaskStatusEnum
    owner_id: str | None = None
    owner_name: str | None = None
    blocked_by: list[str] = Field(default_factory=list)
    write_scopes: list[str] = Field(default_factory=list)
    ready: bool
    write_scope_warnings: list[str] = Field(default_factory=list)


# -----------------------------------------------------------------------------
# Peer Mailbox DTOs
# -----------------------------------------------------------------------------

class SendTeamMessageRequest(BaseModel):
    """Request to send a peer-to-peer message to another teammate."""

    model_config = ConfigDict(extra="forbid")

    sender_name: str = Field(..., description="Sender teammate name in roster")
    target_name: str = Field(..., description="Target teammate name in roster")
    content: str = Field(..., description="Message payload body")
    mode: DeliveryModeEnum = Field(default=DeliveryModeEnum.QUIET, description="Delivery mode: 'quiet' or 'waking'")


class TeamMessageResponse(BaseModel):
    """One peer message snapshot view."""

    model_config = ConfigDict(extra="ignore")

    id: str
    team_id: str
    sender_id: str
    sender_name: str
    target_id: str
    target_name: str
    content: str
    mode: DeliveryModeEnum
    created_at: float
    delivered: bool


class DrainInboxResponse(BaseModel):
    """List of delivered messages after drain."""

    model_config = ConfigDict(extra="ignore")

    member_name: str
    messages: list[TeamMessageResponse]


# -----------------------------------------------------------------------------
# Projection DTO
# -----------------------------------------------------------------------------

class TeamProjectionResponse(BaseModel):
    """Durable Team state projection published to web UI and callers."""

    model_config = ConfigDict(extra="ignore")

    team_id: str
    members: list[TeamMemberResponse]
    tasks: list[TeamTaskResponse]
    failure: str | None = None
