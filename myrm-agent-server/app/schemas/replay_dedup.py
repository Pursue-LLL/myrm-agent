"""Pydantic V2 schemas for Multi-Agent Tool Replay History Deduplication & Status Harmonization (Item 57).

[INPUT]
- MergeReplayHistoryRequest, SyncSubagentStatusRequest, HeartbeatLeaseCheckRequest.

[OUTPUT]
- ToolReplayItemDTO, MergedReplayBatchDTO, MergeReplayHistoryResponse,
  SyncSubagentStatusResponse, HeartbeatLeaseCheckResponse.

[POS]
- Server-side typed DTO schemas for compacting consecutive read-only tool history,
  enforcing monotonic subagent status machines, and preventing UI deadlocks.
"""

from __future__ import annotations

import enum

from pydantic import BaseModel, ConfigDict, Field


class ToolReplayStatusDTOEnum(enum.StrEnum):
    """Lifecycle status classification for subagent tool execution."""

    IDLE = "idle"
    RUNNING = "running"
    PENDING_APPROVAL = "pending_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMEOUT_TERMINATED = "timeout_terminated"


class ToolReplayKindDTOEnum(enum.StrEnum):
    """Semantic classification of tool operation effects."""

    READ_ONLY = "read_only"
    MUTATING = "mutating"
    SYSTEM = "system"


class ToolReplayItemDTO(BaseModel):
    """Individual atomic tool execution record."""

    model_config = ConfigDict(frozen=True)

    call_id: str = Field(..., description="Unique tool call execution identifier")
    tool_name: str = Field(..., description="Name of the invoked tool")
    kind: ToolReplayKindDTOEnum = Field(..., description="Semantic effect classification")
    args: dict[str, str | int | float | bool] = Field(
        default_factory=dict,
        description="Tool invocation argument map (strictly typed, no Any)",
    )
    result_summary: str = Field(..., description="Compact summary of execution result")
    status: ToolReplayStatusDTOEnum = Field(..., description="Execution status")
    start_time: float = Field(..., description="Start epoch timestamp")
    end_time: float = Field(..., description="End epoch timestamp")
    estimated_tokens: int = Field(..., ge=0, description="Token consumption footprint")
    subagent_id: str = Field(..., description="Target subagent identifier")


class MergedReplayBatchDTO(BaseModel):
    """Consolidated representation of multiple consecutive idempotent read-only tool calls."""

    model_config = ConfigDict(frozen=True)

    batch_id: str = Field(..., description="Unique batch identifier")
    tool_name: str = Field(..., description="Homogenous tool name consolidated in this batch")
    merged_count: int = Field(..., ge=2, description="Count of merged tool invocations")
    item_ids: list[str] = Field(..., description="Ordered list of original call IDs")
    aggregated_args_summary: str = Field(..., description="Consolidated argument summary")
    aggregated_result_summary: str = Field(..., description="Consolidated result summary")
    original_tokens: int = Field(..., ge=0, description="Cumulative tokens before merging")
    compact_tokens: int = Field(..., ge=0, description="Compressed tokens after batching")
    tokens_saved: int = Field(..., ge=0, description="Net tokens saved by deduplication")
    start_time: float = Field(..., description="Earliest invocation start timestamp")
    end_time: float = Field(..., description="Latest invocation end timestamp")
    final_status: ToolReplayStatusDTOEnum = Field(..., description="Aggregate status outcome")
    subagent_id: str = Field(..., description="Associated subagent identifier")


class MergeReplayHistoryRequest(BaseModel):
    """Payload to compact and deduplicate a sequence of tool replay items."""

    session_id: str = Field(..., description="Parent session identifier")
    items: list[ToolReplayItemDTO] = Field(default_factory=list, description="Sequence of tool items")
    min_merge_count: int = Field(2, ge=2, le=50, description="Minimum consecutive calls to trigger batching")
    max_batch_size: int = Field(20, ge=2, le=100, description="Maximum items aggregated into a single batch")


class MergeReplayHistoryResponse(BaseModel):
    """Aggregated result detailing deduplicated batches and token conservation metrics."""

    model_config = ConfigDict(frozen=True)

    session_id: str = Field(..., description="Parent session identifier")
    original_items_count: int = Field(..., description="Total input items count")
    deduplicated_items_count: int = Field(..., description="Consolidated items count (batches + unmerged)")
    total_original_tokens: int = Field(..., description="Total token footprint before compacting")
    total_compact_tokens: int = Field(..., description="Optimized token footprint after compacting")
    tokens_saved: int = Field(..., description="Net tokens conserved")
    reduction_ratio: float = Field(..., description="Proportional token savings (0.0 - 1.0)")
    batches: list[MergedReplayBatchDTO] = Field(default_factory=list, description="Synthesized batches")
    unmerged_items: list[ToolReplayItemDTO] = Field(default_factory=list, description="Retained unmerged items")


class SyncSubagentStatusRequest(BaseModel):
    """Request to transition subagent status machine."""

    session_id: str = Field(..., description="Parent session identifier")
    subagent_id: str = Field(..., description="Target subagent identifier")
    status: ToolReplayStatusDTOEnum = Field(..., description="Target status to shift into")
    reason: str = Field("", description="Contextual reason for transition")


class SyncSubagentStatusResponse(BaseModel):
    """Record of subagent status transition."""

    model_config = ConfigDict(frozen=True)

    session_id: str = Field(..., description="Parent session identifier")
    subagent_id: str = Field(..., description="Target subagent identifier")
    previous_status: ToolReplayStatusDTOEnum = Field(..., description="Prior state")
    new_status: ToolReplayStatusDTOEnum = Field(..., description="Current state")
    timestamp: float = Field(..., description="Transition timestamp")
    reason: str = Field(..., description="Explanation of transition")
    is_deadlock_prevented: bool = Field(False, description="Whether transition was forced by deadlock watchdog")


class HeartbeatLeaseCheckRequest(BaseModel):
    """Payload to trigger watchdog timeout scan across active subagents."""

    session_id: str = Field(..., description="Parent session identifier")


class HeartbeatLeaseCheckResponse(BaseModel):
    """Summary of watchdog scan and anti-deadlock interventions."""

    model_config = ConfigDict(frozen=True)

    session_id: str = Field(..., description="Parent session identifier")
    interventions_count: int = Field(..., description="Count of hung subagents auto-terminated")
    interventions: list[SyncSubagentStatusResponse] = Field(default_factory=list, description="Watchdog events")
    current_statuses: dict[str, ToolReplayStatusDTOEnum] = Field(
        default_factory=dict,
        description="Snapshot map of all subagent states",
    )
