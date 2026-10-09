"""[POS]: app/api/memory/batch_learn.py
[INPUT]: FastAPI HTTP requests for resilient chunk learning, namespaced item provenance, and undo.
[OUTPUT]: Strongly-typed JSON responses confirming batch distillation reports and item status.
"""

from fastapi import APIRouter, Depends, HTTPException
from myrm_agent_harness.toolkits.memory import (
    BatchMemoryLearningService,
    BatchRawChunk,
    LearnedMemoryItem,
)

from app.schemas.batch_learn import (
    BatchItemsResponse,
    BatchLearnRequest,
    BatchLearnResponse,
    ChunkDiagnosticDTO,
    LearnedItemDTO,
    UndoItemRequest,
    UndoItemResponse,
)
from app.services.memory.batch_learn import get_batch_learning_service

router = APIRouter(prefix="/batch-learn", tags=["memory-batch-learn"])


def _to_item_dto(item: LearnedMemoryItem) -> LearnedItemDTO:
    return LearnedItemDTO(
        namespaced_id=item.namespaced_id,
        batch_id=item.batch_id,
        chunk_index=item.chunk_index,
        content=item.content,
        tags=item.tags,
        layer_recommendation=item.layer_recommendation,
        status=item.status.value,
        created_at=item.created_at,
    )


@router.post("/learn", response_model=BatchLearnResponse)
def execute_batch_learn(
    request: BatchLearnRequest,
    service: BatchMemoryLearningService = Depends(get_batch_learning_service),
) -> BatchLearnResponse:
    """Distill multiple text chunks into canonical memories with per-item namespaced IDs and resilience telemetry."""
    raw_chunks = [
        BatchRawChunk(
            chunk_index=c.chunk_index,
            raw_text=c.raw_text,
            source_metadata=c.metadata,
        )
        for c in request.chunks
    ]

    report = service.learn_batch(
        chunks=raw_chunks,
        scope=request.scope,
        sub_scope=request.sub_scope,
        category=request.category,
    )

    items_dto = [_to_item_dto(item) for item in report.items]
    diagnostics_dto = [
        ChunkDiagnosticDTO(
            chunk_index=diag.chunk_index,
            status=diag.status.value,
            attempt_count=diag.attempt_count,
            elapsed_ms=diag.elapsed_ms,
            extracted_items_count=diag.extracted_items_count,
        )
        for diag in report.chunk_diagnostics
    ]

    return BatchLearnResponse(
        batch_id=report.batch_id,
        total_chunks=report.total_chunks,
        successful_chunks=report.successful_chunks,
        retried_chunks=report.retried_chunks,
        failed_chunks=report.failed_chunks,
        total_items_learned=report.total_items_learned,
        items=items_dto,
        chunk_diagnostics=diagnostics_dto,
    )


@router.post("/undo", response_model=UndoItemResponse)
def undo_learned_item(
    request: UndoItemRequest,
    service: BatchMemoryLearningService = Depends(get_batch_learning_service),
) -> UndoItemResponse:
    """Revoke a specific learned memory item by its namespaced ID without invalidating the parent batch."""
    success = service.undo_item_by_namespaced_id(request.namespaced_id)
    msg = (
        f"Memory item {request.namespaced_id} successfully revoked."
        if success
        else f"Memory item {request.namespaced_id} not found or already revoked."
    )
    return UndoItemResponse(
        success=success,
        namespaced_id=request.namespaced_id,
        message=msg,
    )


@router.get("/item/{namespaced_id}", response_model=LearnedItemDTO)
def get_learned_item(
    namespaced_id: str,
    service: BatchMemoryLearningService = Depends(get_batch_learning_service),
) -> LearnedItemDTO:
    """Retrieve details and lifecycle status of a specific namespaced memory item."""
    item = service.get_item_by_namespaced_id(namespaced_id)
    if not item:
        raise HTTPException(status_code=404, detail=f"Namespaced item {namespaced_id} not found")
    return _to_item_dto(item)


@router.get("/batch/{batch_id}/items", response_model=BatchItemsResponse)
def list_batch_items(
    batch_id: str,
    service: BatchMemoryLearningService = Depends(get_batch_learning_service),
) -> BatchItemsResponse:
    """Retrieve all memory items created under a specific batch identifier."""
    items = service.list_items_by_batch(batch_id)
    dtos = [_to_item_dto(it) for it in items]
    return BatchItemsResponse(
        batch_id=batch_id,
        total_items=len(dtos),
        items=dtos,
    )
