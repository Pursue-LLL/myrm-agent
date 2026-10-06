"""
[POS] app/api/memory/budget_curator.py
[INPUT] fastapi, app.schemas.memory_budget_curator, app.services.memory.memory_budget_curator_service
[OUTPUT] router

FastAPI router exposing endpoints for Memory Budget Meter, Atomic Operations Curator, and Session Scroll Navigator.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, ConfigDict, Field

from app.schemas.memory_budget_curator import (
    AtomicBatchRequestDTO,
    AtomicBatchResponseDTO,
    ManagedMemoryItemDTO,
    MemoryBudgetSpecDTO,
    MemoryBudgetStatusDTO,
    ScrollAnchorRequestDTO,
    ScrollAnchorResponseDTO,
    ScrollMessageItemDTO,
)
from app.services.memory.memory_budget_curator_service import (
    MemoryBudgetCuratorService,
    get_memory_budget_curator_service,
)

router = APIRouter()


class EvaluateBudgetPayloadDTO(BaseModel):
    """Payload to evaluate memory items budget."""

    model_config = ConfigDict(extra="forbid")

    items: list[ManagedMemoryItemDTO] = Field(
        default_factory=list, description="List of memory items"
    )
    spec: MemoryBudgetSpecDTO | None = Field(
        default=None, description="Optional custom budget spec"
    )


class SessionScrollPayloadDTO(BaseModel):
    """Payload to traverse conversation around an anchor message."""

    model_config = ConfigDict(extra="forbid")

    messages: list[ScrollMessageItemDTO] = Field(
        default_factory=list, description="Historical messages slice"
    )
    request: ScrollAnchorRequestDTO = Field(
        ..., description="Anchor navigation request parameters"
    )


@router.post(
    "/budget/evaluate",
    response_model=MemoryBudgetStatusDTO,
    status_code=status.HTTP_200_OK,
    summary="Evaluate memory budget utilization and generate visual header",
)
def evaluate_memory_budget(
    payload: EvaluateBudgetPayloadDTO,
    service: MemoryBudgetCuratorService = Depends(get_memory_budget_curator_service),
) -> MemoryBudgetStatusDTO:
    """Evaluate token and slot consumption and render a prompt-injectable budget dashboard header."""
    return service.evaluate_budget(payload.items, payload.spec)


@router.post(
    "/budget/atomic-batch",
    response_model=AtomicBatchResponseDTO,
    status_code=status.HTTP_200_OK,
    summary="Atomically apply a batch of memory additions, removals, and replacements",
)
def apply_atomic_batch_operations(
    request: AtomicBatchRequestDTO,
    service: MemoryBudgetCuratorService = Depends(get_memory_budget_curator_service),
) -> AtomicBatchResponseDTO:
    """Execute memory curation operations atomically, reverting completely if budget overflows or collisions occur."""
    return service.apply_atomic_batch(request)


@router.post(
    "/sessions/scroll",
    response_model=ScrollAnchorResponseDTO,
    status_code=status.HTTP_200_OK,
    summary="Traverse conversation history around a target message ID",
)
def scroll_session_around_anchor(
    payload: SessionScrollPayloadDTO,
    service: MemoryBudgetCuratorService = Depends(get_memory_budget_curator_service),
) -> ScrollAnchorResponseDTO:
    """Extract a continuous sliding window of messages preceding and succeeding a target anchor message ID."""
    return service.scroll_around_message(payload.messages, payload.request)
