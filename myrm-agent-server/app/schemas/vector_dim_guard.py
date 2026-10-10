"""Schemas for vector index dimension guard and task-based rebuild orchestration.

[INPUT]
- Pydantic BaseModel, collection specifications, dimensions, and task payloads.

[OUTPUT]
- DimGuardInspectRequestDTO, DimGuardInspectResponseDTO, StartRebuildRequestDTO,
  FailedItemDTO, RebuildTaskStatusResponseDTO.

[POS]
- Server-side DTO contracts for Item 151 VectorDimGuardAndRebuildTaskSuite.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class DimGuardInspectRequestDTO(BaseModel):
    """Payload to inspect dimensionality of a vector collection."""

    collection: str = Field(..., description="Vector collection identifier")
    expected_dim: int = Field(..., description="Expected vector embedding dimension")


class DimGuardInspectResponseDTO(BaseModel):
    """Inspection outcome indicating dimension match and rebuild necessity."""

    collection: str
    exists: bool
    current_dim: int | None
    expected_dim: int
    dim_match: bool
    needs_rebuild: bool
    data_intact: bool
    message: str


class StartRebuildRequestDTO(BaseModel):
    """Payload to initiate a task-based non-destructive vector index rebuild."""

    collection: str = Field(..., description="Target vector collection identifier")
    expected_dim: int = Field(..., description="New expected vector embedding dimension")
    items: list[dict[str, str | list[float]]] = Field(
        default_factory=list, description="Documents to re-index during rebuild"
    )
    fail_item_ids: list[str] = Field(
        default_factory=list, description="Optional IDs to simulate embedding failure for testing"
    )


class FailedItemDTO(BaseModel):
    """Details of an individual item that failed during rebuild."""

    item_id: str
    reason: str
    phase: str
    timestamp_ms: int


class RebuildTaskStatusResponseDTO(BaseModel):
    """Real-time status snapshot of a vector rebuild task."""

    task_id: str
    collection: str
    phase: str
    progress_pct: int
    processed_count: int
    total_count: int
    failed_items: list[FailedItemDTO]
    started_at_ms: int
    finished_at_ms: int | None
    error: str | None
