"""Pydantic V2 schemas for Multi-Agent Visual Timeline & Cherry-Pick Rollback (Item 61).

[INPUT]
- TimelineNodeRecordRequest, TimelineFilterCriteriaRequest.

[OUTPUT]
- TimelineNodeDTO, RollbackResultDTO, TimelineQueryResponseDTO.

[POS]
- Server-side DTO layer for Item 61 surgical non-destructive multi-agent rollback.
"""

from __future__ import annotations

import enum

from pydantic import BaseModel, ConfigDict, Field


class ActorTypeDTOEnum(enum.StrEnum):
    """Classification of event initiator."""

    HUMAN_USER = "human_user"
    LOCAL_AGENT = "local_agent"
    CLOUD_AGENT = "cloud_agent"
    SYSTEM_ORCHESTRATOR = "system_orchestrator"


class OperationTypeDTOEnum(enum.StrEnum):
    """Category of atomic mutation on the workspace/filesystem."""

    FILE_MODIFY = "file_modify"
    FILE_CREATE = "file_create"
    FILE_DELETE = "file_delete"
    TOOL_EXECUTION = "tool_execution"
    GIT_COMMIT = "git_commit"


class RollbackStatusDTOEnum(enum.StrEnum):
    """Outcome status of an atomic cherry-pick rollback attempt."""

    SUCCESS = "success"
    CONFLICT_DETECTED = "conflict_detected"
    ALREADY_ROLLED_BACK = "already_rolled_back"
    NODE_NOT_FOUND = "node_not_found"


class TimelineNodeRecordRequest(BaseModel):
    """Request payload to record an atomic action node to the timeline."""

    model_config = ConfigDict(frozen=True)

    session_id: str = Field(..., min_length=1, description="Associated multi-agent session ID")
    actor_id: str = Field(..., min_length=1, description="ID of the actor (subagent or human)")
    actor_name: str = Field(..., min_length=1, description="Display name of the actor")
    actor_type: ActorTypeDTOEnum = Field(default=ActorTypeDTOEnum.LOCAL_AGENT)
    operation_type: OperationTypeDTOEnum = Field(default=OperationTypeDTOEnum.FILE_MODIFY)
    file_path: str = Field(default="", description="Target file path if applicable")
    line_start: int | None = Field(default=None, ge=1, description="Starting line modified")
    line_end: int | None = Field(default=None, ge=1, description="Ending line modified")
    before_content: str = Field(default="", description="File content before change")
    after_content: str = Field(default="", description="File content after change")
    diff_summary: str = Field(default="", description="Human-readable description/diff of change")
    parent_node_id: str | None = Field(default=None, description="Preceding node dependency")
    metadata: dict[str, str] = Field(default_factory=dict, description="Custom tags and metadata")


class TimelineNodeDTO(BaseModel):
    """Data Transfer Object representing a timeline node."""

    model_config = ConfigDict(frozen=True)

    node_id: str = Field(..., description="Unique atomic node identifier")
    session_id: str = Field(...)
    actor_id: str = Field(...)
    actor_name: str = Field(...)
    actor_type: ActorTypeDTOEnum = Field(...)
    operation_type: OperationTypeDTOEnum = Field(...)
    file_path: str = Field(default="")
    line_start: int | None = Field(default=None)
    line_end: int | None = Field(default=None)
    before_content: str = Field(default="")
    after_content: str = Field(default="")
    diff_summary: str = Field(default="")
    parent_node_id: str | None = Field(default=None)
    is_rolled_back: bool = Field(default=False)
    timestamp: float = Field(...)
    metadata: dict[str, str] = Field(default_factory=dict)


class TimelineFilterCriteriaRequest(BaseModel):
    """Query filter parameters for timeline nodes."""

    model_config = ConfigDict(frozen=True)

    session_id: str = Field(..., min_length=1, description="Session ID to query")
    actor_id: str | None = Field(default=None)
    actor_type: ActorTypeDTOEnum | None = Field(default=None)
    operation_type: OperationTypeDTOEnum | None = Field(default=None)
    file_path: str | None = Field(default=None)
    start_time: float | None = Field(default=None)
    end_time: float | None = Field(default=None)


class RollbackResultDTO(BaseModel):
    """DTO representing the result of an atomic cherry-pick rollback."""

    model_config = ConfigDict(frozen=True)

    node_id: str = Field(...)
    status: RollbackStatusDTOEnum = Field(...)
    file_path: str = Field(default="")
    restored_content: str = Field(default="")
    conflict_reason: str | None = Field(default=None)
    rollback_timestamp: float = Field(...)
