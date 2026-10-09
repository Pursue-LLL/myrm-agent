"""[POS]: app/api/memory/cognitive_box.py
[INPUT]: HTTP requests for cognitive memory entries, intake screening, and snapshots.
[OUTPUT]: FastAPI APIRouter endpoints for cognitive context box management.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from myrm_agent_harness.toolkits.memory import (
    CognitiveLayerKind,
    CognitiveMemoryBoxService,
    CognitiveMemoryEntry,
)

from app.schemas.cognitive_box import (
    ClearLayerResponse,
    CognitiveBoxSnapshotResponse,
    CognitiveEntryDTO,
    EvaluateIntakeRequest,
    IntakeReportResponse,
    WriteDirectEntryRequest,
)
from app.services.memory.cognitive_box import get_cognitive_box_service

router = APIRouter(prefix="/cognitive-box", tags=["memory-cognitive-box"])


def _to_dto(entry: CognitiveMemoryEntry) -> CognitiveEntryDTO:
    return CognitiveEntryDTO(
        id=entry.id,
        layer=entry.layer.value,
        content=entry.content,
        confidence=entry.confidence,
        tags=list(entry.tags),
        created_at=entry.created_at,
        updated_at=entry.updated_at,
        source_session=entry.source_session,
    )


@router.get("/entries", response_model=list[CognitiveEntryDTO])
def list_cognitive_entries(
    layer: str | None = None,
    limit: int = 100,
    service: CognitiveMemoryBoxService = Depends(get_cognitive_box_service),
) -> list[CognitiveEntryDTO]:
    """List cognitive entries, optionally filtered by layer."""
    target_layer = None
    if layer:
        try:
            target_layer = CognitiveLayerKind(layer)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid layer: {layer}. Must be one of {[k.value for k in CognitiveLayerKind]}",
            ) from None

    entries = service.get_entries(layer=target_layer, limit=limit)
    return [_to_dto(e) for e in entries]


@router.post("/evaluate", response_model=IntakeReportResponse)
def evaluate_and_ingest(
    request: EvaluateIntakeRequest,
    service: CognitiveMemoryBoxService = Depends(get_cognitive_box_service),
) -> IntakeReportResponse:
    """Evaluate candidate text against strict intake filter and record if admitted."""
    forced_layer = None
    if request.forced_layer:
        try:
            forced_layer = CognitiveLayerKind(request.forced_layer)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid forced_layer: {request.forced_layer}",
            ) from None

    report, entry = service.evaluate_and_ingest(
        raw_content=request.content,
        source_session=request.source_session,
        forced_layer=forced_layer,
        tags=request.tags,
    )

    return IntakeReportResponse(
        decision=report.decision.value,
        layer=report.layer.value if report.layer else None,
        confidence=report.confidence,
        reason=report.reason,
        sanitized_content=report.sanitized_content,
        existing_entry_id=report.existing_entry_id,
        admitted_entry=_to_dto(entry) if entry else None,
    )


@router.post("/write", response_model=CognitiveEntryDTO)
def write_direct_entry(
    request: WriteDirectEntryRequest,
    service: CognitiveMemoryBoxService = Depends(get_cognitive_box_service),
) -> CognitiveEntryDTO:
    """Directly record an entry into a cognitive layer (e.g. identity or environment setup)."""
    try:
        layer_kind = CognitiveLayerKind(request.layer)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid layer: {request.layer}") from None

    entry_id = request.id or f"cog_{uuid.uuid4().hex[:12]}"
    entry = CognitiveMemoryEntry(
        id=entry_id,
        layer=layer_kind,
        content=request.content.strip(),
        confidence=request.confidence,
        tags=request.tags,
        source_session=request.source_session,
    )
    saved = service.write_direct_entry(entry)
    return _to_dto(saved)


@router.get("/snapshot", response_model=CognitiveBoxSnapshotResponse)
def get_box_snapshot(
    service: CognitiveMemoryBoxService = Depends(get_cognitive_box_service),
) -> CognitiveBoxSnapshotResponse:
    """Return aggregated snapshot and counts across all cognitive layers."""
    snapshot = service.get_snapshot()
    return CognitiveBoxSnapshotResponse(
        timestamp=snapshot.timestamp,
        total_count=snapshot.total_count,
        counts_by_layer=snapshot.counts_by_layer,
        entries=[_to_dto(e) for e in snapshot.entries],
    )


@router.get("/prompt-context")
def get_prompt_context(
    service: CognitiveMemoryBoxService = Depends(get_cognitive_box_service),
) -> dict[str, str]:
    """Render structured cognitive context block for system prompt injection."""
    return {"prompt_context": service.render_prompt_context()}


@router.delete("/layer/{layer}", response_model=ClearLayerResponse)
def clear_layer(
    layer: str,
    service: CognitiveMemoryBoxService = Depends(get_cognitive_box_service),
) -> ClearLayerResponse:
    """Purge all entries belonging to a specific cognitive layer."""
    try:
        layer_kind = CognitiveLayerKind(layer)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid layer: {layer}") from None

    purged = service.clear_layer(layer_kind)
    return ClearLayerResponse(layer=layer_kind.value, purged_count=purged)
