"""Pydantic V2 schemas for Pi Harness v2 Multi-Lane Parallel Execution Model (Item 50).

[INPUT]
- CreateLaneRequest, AppendNodeRequest, DispatchOperationRequest,
  CompleteOperationRequest, CancelOperationRequest.

[OUTPUT]
- TreeNodeDTO, LaneOperationDTO, LaneInfoDTO, MultiLaneSnapshotDTO.

[POS]
- Server-side typed DTO schemas for session multi-lane parallel coordination.
"""

from __future__ import annotations

import enum

from pydantic import BaseModel, ConfigDict, Field

PrimitiveValue = str | int | float | bool | None


class LaneStateEnum(enum.StrEnum):
    """Execution state of a lane within a session."""

    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    CLOSED = "closed"


class OpStatusEnum(enum.StrEnum):
    """Lifecycle status of an operation on a lane."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TreeNodeDTO(BaseModel):
    """DTO representing a single node in the shared append-only tree."""

    model_config = ConfigDict(frozen=True)

    node_id: str = Field(..., description="Unique node identifier")
    parent_id: str | None = Field(default=None, description="Parent node identifier")
    lane_id: str = Field(..., description="Originating lane identifier")
    node_type: str = Field(..., description="Type of node, e.g. message, tool_result, root")
    content: str = Field(..., description="Content payload of the node")
    created_at: float = Field(..., description="Creation timestamp in epoch seconds")
    metadata: dict[str, PrimitiveValue] = Field(default_factory=dict, description="Metadata dictionary")


class LaneOperationDTO(BaseModel):
    """DTO representing an operation entry on a lane."""

    model_config = ConfigDict(frozen=True)

    op_id: str = Field(..., description="Unique operation identifier")
    lane_id: str = Field(..., description="Associated lane identifier")
    name: str = Field(..., description="Name of the operation")
    payload: dict[str, PrimitiveValue] = Field(default_factory=dict, description="Operation parameters")
    status: OpStatusEnum = Field(..., description="Lifecycle status")
    created_at: float = Field(..., description="Creation epoch timestamp")
    started_at: float | None = Field(default=None, description="Start epoch timestamp")
    completed_at: float | None = Field(default=None, description="Completion epoch timestamp")
    error_message: str | None = Field(default=None, description="Failure or cancellation message")
    result_node_id: str | None = Field(default=None, description="Appended result tree node ID")


class LaneInfoDTO(BaseModel):
    """DTO representing a single lane's state and pointer."""

    model_config = ConfigDict(frozen=True)

    lane_id: str = Field(..., description="Unique lane key, e.g. main or slack:thread_123")
    display_name: str = Field(..., description="Human readable title for the lane")
    state: LaneStateEnum = Field(..., description="Current lane state")
    current_leaf_id: str = Field(..., description="ID of current leaf node in shared tree")
    active_op_id: str | None = Field(default=None, description="ID of currently running operation")
    total_ops: int = Field(default=0, description="Total operations executed on lane")
    created_at: float = Field(..., description="Creation epoch timestamp")


class CreateLaneRequest(BaseModel):
    """Request to initialize or register a new lane in the session."""

    lane_id: str = Field(..., min_length=1, max_length=128, description="Lane key, e.g. slack:thread-42")
    display_name: str = Field(..., min_length=1, max_length=256, description="Human friendly lane title")
    fork_from_node_id: str | None = Field(default=None, description="Optional parent node to fork leaf from")


class AppendNodeRequest(BaseModel):
    """Request to manually append a message/marker node to a lane's branch."""

    content: str = Field(..., min_length=1, max_length=10000, description="Node content")
    node_type: str = Field(default="message", description="Node type tag")
    metadata: dict[str, PrimitiveValue] = Field(default_factory=dict, description="Optional metadata")


class DispatchOperationRequest(BaseModel):
    """Request to schedule an operation on a lane."""

    name: str = Field(..., min_length=1, max_length=128, description="Operation name")
    payload: dict[str, PrimitiveValue] = Field(default_factory=dict, description="Operation arguments")


class CompleteOperationRequest(BaseModel):
    """Request to complete an in-flight operation."""

    op_id: str = Field(..., description="Target operation ID")
    result_content: str | None = Field(default=None, description="Optional text result to append to tree")
    error: str | None = Field(default=None, description="Error message if operation failed")


class CancelOperationRequest(BaseModel):
    """Request to cancel an in-flight operation."""

    op_id: str = Field(..., description="Target operation ID")
    reason: str | None = Field(default=None, description="Cancellation reason")


class MultiLaneSnapshotDTO(BaseModel):
    """Global snapshot response containing all lanes and topology stats."""

    model_config = ConfigDict(frozen=True)

    session_id: str = Field(..., description="Associated session / chat identifier")
    lanes: dict[str, LaneInfoDTO] = Field(..., description="Active lanes dictionary keyed by lane_id")
    total_nodes: int = Field(..., description="Total nodes count in shared append-only tree")
    active_lanes_count: int = Field(..., description="Number of currently running lanes")
    recent_op_logs: list[LaneOperationDTO] = Field(..., description="Chronological recent operation logs")
