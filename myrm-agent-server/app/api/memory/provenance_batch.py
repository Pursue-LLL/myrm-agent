"""
[POS] app/api/memory/provenance_batch.py
[INPUT] fastapi, app.schemas.memory_provenance_batch, app.services.memory.memory_provenance_batch_service
[OUTPUT] router

FastAPI router exposing endpoints for Skill Memory Extraction Provenance and Batch Learn Namespace Isolation.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from app.schemas.memory_provenance_batch import (
    BatchLearnRequestDTO,
    BatchLearnResponseDTO,
    CreateProvenanceLinkRequestDTO,
    ExtractionProvenanceLinkDTO,
)
from app.services.memory.memory_provenance_batch_service import (
    MemoryProvenanceBatchService,
    get_memory_provenance_batch_service,
)

router = APIRouter()


@router.post(
    "/provenance/link",
    response_model=ExtractionProvenanceLinkDTO,
    status_code=status.HTTP_200_OK,
    summary="Create and anchor an immutable extraction provenance link with physical tool execution traces",
)
def create_provenance_link(
    request: CreateProvenanceLinkRequestDTO,
    service: MemoryProvenanceBatchService = Depends(get_memory_provenance_batch_service),
) -> ExtractionProvenanceLinkDTO:
    """Anchor an extracted skill memory to concrete turn prompt and tool execution traces."""
    return service.create_provenance_link(request)


@router.post(
    "/batch-learn/isolate",
    response_model=BatchLearnResponseDTO,
    status_code=status.HTTP_200_OK,
    summary="Isolate batch learning submissions by injecting collision-free namespaced IDs",
)
def isolate_batch_learning(
    request: BatchLearnRequestDTO,
    service: MemoryProvenanceBatchService = Depends(get_memory_provenance_batch_service),
) -> BatchLearnResponseDTO:
    """Process batch learning submissions, enforcing namespace hard boundaries between private and shared memory."""
    return service.isolate_batch_learning(request)
