"""Service implementation for High-Concurrency Swarm & Adaptive Cloud Offload (Item 60).

[INPUT]
- SwarmDispatchBatchRequest, HostWatermarkReportRequest, OffloadPolicyUpdateRequest.
- Harness swarm_offload::{
    ResourceWatermarkMonitor, SwarmOffloadDispatcher, OffloadStrategy,
    ExecutionTarget, WorkerState, TaskPriority, SwarmTaskDefinition,
  }

[OUTPUT]
- SwarmBatchSummaryDTO, SwarmWorkerRecordDTO, ResourceWatermarkDTO.

[POS]
- Server-side business service managing 10-15 concurrency swarm batches and
  host resource watermark telemetry.
"""

from __future__ import annotations

import logging
from typing import Final

from myrm_agent_harness.agent.sub_agents.swarm_offload import (
    ExecutionTarget,
    OffloadStrategy,
    ResourceWatermark,
    ResourceWatermarkMonitor,
    SwarmBatchSummary,
    SwarmOffloadDispatcher,
    SwarmTaskDefinition,
    SwarmWorkerRecord,
    TaskPriority,
    WorkerState,
)

from app.schemas.swarm_offload import (
    ExecutionTargetDTOEnum,
    OffloadPolicyUpdateRequest,
    OffloadStrategyDTOEnum,
    ResourceWatermarkDTO,
    SwarmBatchSummaryDTO,
    SwarmDispatchBatchRequest,
    SwarmWorkerRecordDTO,
    TaskPriorityDTOEnum,
    WorkerStateDTOEnum,
)

logger: Final = logging.getLogger(__name__)


def _map_strategy_dto_to_harness(dto: OffloadStrategyDTOEnum) -> OffloadStrategy:
    match dto:
        case OffloadStrategyDTOEnum.ADAPTIVE:
            return OffloadStrategy.ADAPTIVE
        case OffloadStrategyDTOEnum.FORCE_LOCAL:
            return OffloadStrategy.FORCE_LOCAL
        case OffloadStrategyDTOEnum.FORCE_CLOUD:
            return OffloadStrategy.FORCE_CLOUD


def _map_strategy_harness_to_dto(val: OffloadStrategy) -> OffloadStrategyDTOEnum:
    match val:
        case OffloadStrategy.ADAPTIVE:
            return OffloadStrategyDTOEnum.ADAPTIVE
        case OffloadStrategy.FORCE_LOCAL:
            return OffloadStrategyDTOEnum.FORCE_LOCAL
        case OffloadStrategy.FORCE_CLOUD:
            return OffloadStrategyDTOEnum.FORCE_CLOUD


def _map_target_dto_to_harness(dto: ExecutionTargetDTOEnum | None) -> ExecutionTarget | None:
    if dto is None:
        return None
    match dto:
        case ExecutionTargetDTOEnum.LOCAL_HOST:
            return ExecutionTarget.LOCAL_HOST
        case ExecutionTargetDTOEnum.CLOUD_SANDBOX:
            return ExecutionTarget.CLOUD_SANDBOX


def _map_target_harness_to_dto(val: ExecutionTarget) -> ExecutionTargetDTOEnum:
    match val:
        case ExecutionTarget.LOCAL_HOST:
            return ExecutionTargetDTOEnum.LOCAL_HOST
        case ExecutionTarget.CLOUD_SANDBOX:
            return ExecutionTargetDTOEnum.CLOUD_SANDBOX


def _map_state_harness_to_dto(val: WorkerState) -> WorkerStateDTOEnum:
    match val:
        case WorkerState.QUEUED:
            return WorkerStateDTOEnum.QUEUED
        case WorkerState.RUNNING:
            return WorkerStateDTOEnum.RUNNING
        case WorkerState.COMPLETED:
            return WorkerStateDTOEnum.COMPLETED
        case WorkerState.FAILED:
            return WorkerStateDTOEnum.FAILED
        case WorkerState.TIMED_OUT:
            return WorkerStateDTOEnum.TIMED_OUT
        case WorkerState.CANCELLED:
            return WorkerStateDTOEnum.CANCELLED


def _map_priority_dto_to_harness(dto: TaskPriorityDTOEnum) -> TaskPriority:
    match dto:
        case TaskPriorityDTOEnum.HIGH:
            return TaskPriority.HIGH
        case TaskPriorityDTOEnum.NORMAL:
            return TaskPriority.NORMAL
        case TaskPriorityDTOEnum.LOW:
            return TaskPriority.LOW


def _map_watermark_to_dto(wm: ResourceWatermark) -> ResourceWatermarkDTO:
    return ResourceWatermarkDTO(
        cpu_percent=wm.cpu_percent,
        memory_percent=wm.memory_percent,
        active_local_workers=wm.active_local_workers,
        max_recommended_local_workers=wm.max_recommended_local_workers,
        cpu_threshold_percent=wm.cpu_threshold_percent,
        memory_threshold_percent=wm.memory_threshold_percent,
        is_over_watermark=wm.is_over_watermark,
        recommendation=_map_target_harness_to_dto(wm.recommendation),
        timestamp=wm.timestamp,
    )


def _map_worker_record_to_dto(rec: SwarmWorkerRecord) -> SwarmWorkerRecordDTO:
    return SwarmWorkerRecordDTO(
        worker_id=rec.worker_id,
        task_id=rec.task_id,
        execution_target=_map_target_harness_to_dto(rec.execution_target),
        state=_map_state_harness_to_dto(rec.state),
        started_at=rec.started_at,
        finished_at=rec.finished_at,
        duration_ms=rec.duration_ms,
        exit_code=rec.exit_code,
        result_payload=rec.result_payload,
        artifact_pointer=rec.artifact_pointer,
        error=rec.error,
    )


def _map_batch_summary_to_dto(summary: SwarmBatchSummary) -> SwarmBatchSummaryDTO:
    return SwarmBatchSummaryDTO(
        batch_id=summary.batch_id,
        total_tasks=summary.total_tasks,
        local_workers_count=summary.local_workers_count,
        cloud_workers_count=summary.cloud_workers_count,
        completed_count=summary.completed_count,
        failed_count=summary.failed_count,
        avg_duration_ms=summary.avg_duration_ms,
        peak_cpu_percent=summary.peak_cpu_percent,
        peak_memory_percent=summary.peak_memory_percent,
        offload_strategy=_map_strategy_harness_to_dto(summary.offload_strategy),
        workers=[_map_worker_record_to_dto(w) for w in summary.workers],
    )


class SwarmOffloadService:
    """Manages high-concurrency swarm dispatches and host resource watermark telemetry."""

    def __init__(self) -> None:
        self._reported_cpu: float = 30.0
        self._reported_mem: float = 45.0
        self._monitor = ResourceWatermarkMonitor(
            cpu_threshold_percent=80.0,
            memory_threshold_percent=80.0,
            max_recommended_local_workers=4,
            custom_sampler=self._dynamic_sampler,
        )
        self._dispatcher = SwarmOffloadDispatcher(
            monitor=self._monitor,
            default_strategy=OffloadStrategy.ADAPTIVE,
            max_concurrency=15,
        )
        self._batches: dict[str, SwarmBatchSummaryDTO] = {}

    def _dynamic_sampler(self) -> tuple[float, float]:
        """Sampler factoring in external reported usage and local worker load."""
        added_cpu = self._monitor._active_local_count * 15.0
        added_mem = self._monitor._active_local_count * 10.0
        return (
            min(100.0, self._reported_cpu + added_cpu),
            min(100.0, self._reported_mem + added_mem),
        )

    def clear(self) -> None:
        """Reset service state for testing."""
        self._reported_cpu = 30.0
        self._reported_mem = 45.0
        self._batches.clear()
        self._monitor.reset_peaks()
        self._dispatcher.set_strategy(OffloadStrategy.ADAPTIVE)

    def get_current_watermark(self) -> ResourceWatermarkDTO:
        """Return the current host physical resource watermark snapshot."""
        wm = self._monitor.sample_watermark()
        return _map_watermark_to_dto(wm)

    def report_host_watermark(self, cpu_percent: float, memory_percent: float) -> ResourceWatermarkDTO:
        """Update host physical resource metrics from local desktop probe."""
        self._reported_cpu = max(0.0, min(100.0, cpu_percent))
        self._reported_mem = max(0.0, min(100.0, memory_percent))
        return self.get_current_watermark()

    def update_policy(self, request: OffloadPolicyUpdateRequest) -> OffloadStrategyDTOEnum:
        """Update global swarm offload strategy."""
        harness_strategy = _map_strategy_dto_to_harness(request.strategy)
        self._dispatcher.set_strategy(harness_strategy)
        return request.strategy

    async def dispatch_batch(self, request: SwarmDispatchBatchRequest) -> SwarmBatchSummaryDTO:
        """Dispatch 10-15 tasks concurrently across local and cloud sandboxes."""
        if request.strategy:
            self._dispatcher.set_strategy(_map_strategy_dto_to_harness(request.strategy))

        harness_tasks = [
            SwarmTaskDefinition(
                task_id=t.task_id,
                title=t.title,
                command_or_prompt=t.command_or_prompt,
                priority=_map_priority_dto_to_harness(t.priority),
                weight=t.weight,
                timeout_seconds=t.timeout_seconds,
                preferred_target=_map_target_dto_to_harness(t.preferred_target),
                metadata=dict(t.metadata),
            )
            for t in request.tasks
        ]

        summary = await self._dispatcher.dispatch_swarm_batch(
            tasks=harness_tasks,
            batch_id=request.batch_id,
        )
        dto = _map_batch_summary_to_dto(summary)
        self._batches[dto.batch_id] = dto
        return dto

    def get_batch(self, batch_id: str) -> SwarmBatchSummaryDTO | None:
        """Lookup previously executed swarm batch summary."""
        return self._batches.get(batch_id)


_GLOBAL_SERVICE_INSTANCE: SwarmOffloadService | None = None


def get_swarm_offload_service() -> SwarmOffloadService:
    """Retrieve or initialize the global SwarmOffloadService singleton."""
    global _GLOBAL_SERVICE_INSTANCE
    if _GLOBAL_SERVICE_INSTANCE is None:
        _GLOBAL_SERVICE_INSTANCE = SwarmOffloadService()
    return _GLOBAL_SERVICE_INSTANCE
