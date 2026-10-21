"""Pydantic V2 schemas for High-Concurrency Swarm & Adaptive Cloud Offload (Item 60).

[INPUT]
- SwarmDispatchBatchRequest, HostWatermarkReportRequest, OffloadPolicyUpdateRequest.

[OUTPUT]
- SwarmBatchSummaryDTO, SwarmWorkerRecordDTO, ResourceWatermarkDTO,
  and standardized responses.

[POS]
- Server-side DTO layer for Item 60 10-15 concurrency subagent swarm scheduling
  and host physical resource preservation.
"""

from __future__ import annotations

import enum

from pydantic import BaseModel, ConfigDict, Field


class OffloadStrategyDTOEnum(enum.StrEnum):
    """Strategy controlling local vs cloud sandbox offloading."""

    ADAPTIVE = "adaptive"
    FORCE_LOCAL = "force_local"
    FORCE_CLOUD = "force_cloud"


class ExecutionTargetDTOEnum(enum.StrEnum):
    """Target execution environment for a swarm subagent worker."""

    LOCAL_HOST = "local_host"
    CLOUD_SANDBOX = "cloud_sandbox"


class WorkerStateDTOEnum(enum.StrEnum):
    """Lifecycle execution state of a swarm subagent worker."""

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    CANCELLED = "cancelled"


class TaskPriorityDTOEnum(enum.StrEnum):
    """Priority level for queued swarm tasks."""

    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"


class SwarmTaskDefinitionDTO(BaseModel):
    """Definition of an individual task within a high-concurrency swarm."""

    model_config = ConfigDict(frozen=True)

    task_id: str = Field(..., description="Unique task identifier")
    title: str = Field(..., description="Task title or role description")
    command_or_prompt: str = Field(..., description="Execution prompt or shell command")
    priority: TaskPriorityDTOEnum = Field(TaskPriorityDTOEnum.NORMAL, description="Task priority")
    weight: float = Field(1.0, ge=0.1, le=10.0, description="Computational weight")
    timeout_seconds: float = Field(30.0, gt=0, le=300.0, description="Max execution timeout in seconds")
    preferred_target: ExecutionTargetDTOEnum | None = Field(None, description="Preferred execution target")
    metadata: dict[str, str] = Field(default_factory=dict, description="Custom metadata tags")


class SwarmDispatchBatchRequest(BaseModel):
    """Request payload to dispatch a batch of 10-15 subagents concurrently."""

    model_config = ConfigDict(frozen=True)

    tasks: list[SwarmTaskDefinitionDTO] = Field(..., min_length=1, max_length=50, description="Tasks to execute")
    batch_id: str | None = Field(None, description="Optional custom batch ID")
    strategy: OffloadStrategyDTOEnum | None = Field(None, description="Optional strategy override")


class SwarmWorkerRecordDTO(BaseModel):
    """Execution status and output record for an individual swarm worker."""

    model_config = ConfigDict(frozen=True)

    worker_id: str = Field(..., description="Worker identifier")
    task_id: str = Field(..., description="Associated task ID")
    execution_target: ExecutionTargetDTOEnum = Field(..., description="Where worker executed")
    state: WorkerStateDTOEnum = Field(..., description="Final worker lifecycle state")
    started_at: float = Field(..., description="Start epoch timestamp")
    finished_at: float | None = Field(None, description="Finish epoch timestamp")
    duration_ms: float = Field(..., description="Execution duration in milliseconds")
    exit_code: int = Field(0, description="Process exit code")
    result_payload: str = Field("", description="Worker stdout or text result summary")
    artifact_pointer: str | None = Field(None, description="Zero-copy artifact pointer (e.g. vault://...)")
    error: str | None = Field(None, description="Error message if failed")


class ResourceWatermarkDTO(BaseModel):
    """Snapshot of host physical resource utilization and offload recommendation."""

    model_config = ConfigDict(frozen=True)

    cpu_percent: float = Field(..., description="Current host CPU utilization percentage")
    memory_percent: float = Field(..., description="Current host memory utilization percentage")
    active_local_workers: int = Field(..., description="Active workers running locally")
    max_recommended_local_workers: int = Field(..., description="Local concurrent worker capacity")
    cpu_threshold_percent: float = Field(..., description="CPU threshold triggering offload")
    memory_threshold_percent: float = Field(..., description="Memory threshold triggering offload")
    is_over_watermark: bool = Field(..., description="Whether host is under excessive resource pressure")
    recommendation: ExecutionTargetDTOEnum = Field(..., description="Recommended execution target")
    timestamp: float = Field(..., description="Sample timestamp")


class SwarmBatchSummaryDTO(BaseModel):
    """Aggregated outcome of a high-concurrency swarm dispatch batch."""

    model_config = ConfigDict(frozen=True)

    batch_id: str = Field(..., description="Batch identifier")
    total_tasks: int = Field(..., description="Total tasks in batch")
    local_workers_count: int = Field(..., description="Workers executed on local host")
    cloud_workers_count: int = Field(..., description="Workers offloaded to cloud sandbox")
    completed_count: int = Field(..., description="Tasks successfully completed")
    failed_count: int = Field(..., description="Tasks failed or timed out")
    avg_duration_ms: float = Field(..., description="Average worker duration in milliseconds")
    peak_cpu_percent: float = Field(..., description="Peak CPU observed during batch")
    peak_memory_percent: float = Field(..., description="Peak memory observed during batch")
    offload_strategy: OffloadStrategyDTOEnum = Field(..., description="Active offloading strategy")
    workers: list[SwarmWorkerRecordDTO] = Field(default_factory=list, description="Worker execution records")


class HostWatermarkReportRequest(BaseModel):
    """Request payload for local agent reporting host resource metrics."""

    model_config = ConfigDict(frozen=True)

    cpu_percent: float = Field(..., ge=0.0, le=100.0, description="Host CPU percent")
    memory_percent: float = Field(..., ge=0.0, le=100.0, description="Host memory percent")


class OffloadPolicyUpdateRequest(BaseModel):
    """Request payload to change global offloading policy."""

    model_config = ConfigDict(frozen=True)

    strategy: OffloadStrategyDTOEnum = Field(..., description="New offload strategy")
