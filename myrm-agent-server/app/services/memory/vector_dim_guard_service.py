"""Vector dimension guard and rebuild orchestration business service.

[INPUT]
- DimGuardInspectRequestDTO, StartRebuildRequestDTO from schemas.
- VectorDimGuard, VectorRebuildOrchestrator from harness vector_dim_guard.

[OUTPUT]
- VectorDimGuardService mediating dimensionality checks, task-based rebuilds, and progress tracking.

[POS]
- Server-side domain service for Item 151 VectorDimGuardAndRebuildTaskSuite.
"""

from __future__ import annotations

import logging

from myrm_agent_harness.toolkits.memory.vector_dim_guard import (
    VectorDimGuard,
    VectorRebuildOrchestrator,
)

from app.schemas.vector_dim_guard import (
    DimGuardInspectRequestDTO,
    DimGuardInspectResponseDTO,
    FailedItemDTO,
    RebuildTaskStatusResponseDTO,
    StartRebuildRequestDTO,
)

logger = logging.getLogger(__name__)


class VectorDimGuardService:
    """Service managing vector dimension guard validation and task-based rebuilds."""

    def __init__(self) -> None:
        self._guard = VectorDimGuard()
        self._orchestrator = VectorRebuildOrchestrator(self._guard)

    @property
    def guard(self) -> VectorDimGuard:
        """Access the underlying dimension guard."""
        return self._guard

    @property
    def orchestrator(self) -> VectorRebuildOrchestrator:
        """Access the underlying rebuild orchestrator."""
        return self._orchestrator

    def inspect_dim(self, req: DimGuardInspectRequestDTO) -> DimGuardInspectResponseDTO:
        """Inspect dimensionality alignment for a vector collection."""
        res = self._guard.inspect_dim(req.collection, req.expected_dim)
        return DimGuardInspectResponseDTO(
            collection=res.collection,
            exists=res.exists,
            current_dim=res.current_dim,
            expected_dim=res.expected_dim,
            dim_match=res.dim_match,
            needs_rebuild=res.needs_rebuild,
            data_intact=res.data_intact,
            message=res.message,
        )

    def start_rebuild(self, req: StartRebuildRequestDTO) -> RebuildTaskStatusResponseDTO:
        """Initiate an orchestrated vector rebuild task holding the concurrency lock."""
        status = self._orchestrator.start_rebuild(
            collection=req.collection,
            expected_dim=req.expected_dim,
            items=req.items,
            fail_item_ids=set(req.fail_item_ids),
        )
        return self._to_status_dto(status)

    def get_task_status(self, task_id: str) -> RebuildTaskStatusResponseDTO | None:
        """Retrieve real-time snapshot of a rebuild task."""
        status = self._orchestrator.get_task_status(task_id)
        return self._to_status_dto(status) if status is not None else None

    def get_active_task_id(self) -> str | None:
        """Return the task ID currently holding the rebuild lock, or None."""
        return self._orchestrator.get_active_task_id()

    def _to_status_dto(self, status) -> RebuildTaskStatusResponseDTO:
        return RebuildTaskStatusResponseDTO(
            task_id=status.task_id,
            collection=status.collection,
            phase=status.phase.value,
            progress_pct=status.progress_pct,
            processed_count=status.processed_count,
            total_count=status.total_count,
            failed_items=[
                FailedItemDTO(
                    item_id=fi.item_id,
                    reason=fi.reason,
                    phase=fi.phase,
                    timestamp_ms=fi.timestamp_ms,
                )
                for fi in status.failed_items
            ],
            started_at_ms=status.started_at_ms,
            finished_at_ms=status.finished_at_ms,
            error=status.error,
        )


_instance: VectorDimGuardService | None = None


def get_vector_dim_guard_service() -> VectorDimGuardService:
    """Return the singleton instance of VectorDimGuardService."""
    global _instance
    if _instance is None:
        _instance = VectorDimGuardService()
    return _instance


def reset_vector_dim_guard_service() -> None:
    """Reset the singleton instance (used for testing)."""
    global _instance
    _instance = None
