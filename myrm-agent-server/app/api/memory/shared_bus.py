"""
[POS] app/api/memory/shared_bus.py
[INPUT] fastapi, app.schemas.memory_shared_bus, app.services.memory.memory_shared_bus_service
[OUTPUT] router

FastAPI router exposing endpoints for Multi-Agent Shared Memory Bus, Concurrency Pool, Backpressure Guard, and Negative Decision Ledger.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status

from app.schemas.memory_shared_bus import (
    ConcurrencyPoolStatusResponseDTO,
    MemoryScoreRequestDTO,
    MemoryScoreResponseDTO,
    NegativeDecisionCheckRequestDTO,
    NegativeDecisionCheckResponseDTO,
    NegativeDecisionCreateRequestDTO,
    NegativeDecisionDTO,
)
from app.services.memory.memory_shared_bus_service import (
    MemorySharedBusService,
    get_memory_shared_bus_service,
)

router = APIRouter()


@router.post(
    "/shared-bus/veto",
    response_model=NegativeDecisionDTO,
    status_code=status.HTTP_201_CREATED,
    summary="Record a vetoed technical decision into the negative decision ledger",
)
def record_negative_decision(
    request: NegativeDecisionCreateRequestDTO,
    service: MemorySharedBusService = Depends(get_memory_shared_bus_service),
) -> NegativeDecisionDTO:
    """Record a rejected proposal to prevent downstream agents from repeatedly proposing it."""
    return service.record_veto(request)


@router.post(
    "/shared-bus/check-veto",
    response_model=NegativeDecisionCheckResponseDTO,
    status_code=status.HTTP_200_OK,
    summary="Screen a candidate design proposal against historical negative decision vetoes",
)
def check_negative_decision(
    request: NegativeDecisionCheckRequestDTO,
    service: MemorySharedBusService = Depends(get_memory_shared_bus_service),
) -> NegativeDecisionCheckResponseDTO:
    """Screen candidate proposals against veto history, returning guard prompts and hard-blocking if necessary."""
    return service.check_veto(request)


@router.get(
    "/shared-bus/vetoes",
    response_model=list[NegativeDecisionDTO],
    status_code=status.HTTP_200_OK,
    summary="List active veto records in the negative decision ledger",
)
def list_negative_decisions(
    scope: str | None = Query(default=None, description="Optional scope filter"),
    service: MemorySharedBusService = Depends(get_memory_shared_bus_service),
) -> list[NegativeDecisionDTO]:
    """Retrieve all or scoped historical negative decision entries."""
    return service.list_vetoes(scope=scope)


@router.get(
    "/shared-bus/pool-status",
    response_model=ConcurrencyPoolStatusResponseDTO,
    status_code=status.HTTP_200_OK,
    summary="Query live concurrency pool and memory backpressure guard metrics",
)
def get_concurrency_pool_status(
    service: MemorySharedBusService = Depends(get_memory_shared_bus_service),
) -> ConcurrencyPoolStatusResponseDTO:
    """Get real-time concurrency counters, queue depths, and process RSS backpressure status."""
    return service.get_pool_status()


@router.post(
    "/shared-bus/score",
    response_model=MemoryScoreResponseDTO,
    status_code=status.HTTP_200_OK,
    summary="Evaluate access frequency reinforcement and half-life decay score",
)
def score_memory(
    request: MemoryScoreRequestDTO,
    service: MemorySharedBusService = Depends(get_memory_shared_bus_service),
) -> MemoryScoreResponseDTO:
    """Compute the self-learning composite ranking score using frequency logarithmic reinforcement and exponential half-life decay."""
    return service.score_memory(request)
