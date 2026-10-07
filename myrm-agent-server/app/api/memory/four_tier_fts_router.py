"""[POS]: app/api/memory/four_tier_fts_router.py
[INPUT]: FastAPI APIRouter, Depends, HTTPException, Query, and four-tier schemas.
[OUTPUT]: API router exposing endpoints for four-tier persistent memory, FTS5 BM25 search, and dream compaction.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from app.schemas.four_tier_fts import (
    DreamCompactionReportDTO,
    FourTierMemoryItemDTO,
    FtsSearchResultDTO,
    RunDreamCompactionRequestDTO,
    SaveFourTierMemoryRequestDTO,
)
from app.services.memory.four_tier_fts_service import (
    FourTierFtsService,
    get_four_tier_fts_service,
)

router = APIRouter(prefix="/four-tier", tags=["memory-four-tier-fts"])


@router.post("/items", response_model=FourTierMemoryItemDTO)
async def save_item(
    request: SaveFourTierMemoryRequestDTO,
    service: FourTierFtsService = Depends(get_four_tier_fts_service),
) -> FourTierMemoryItemDTO:
    """Saves or updates a four-tier memory item across project, session, progress, or global scope."""
    try:
        return service.save_item(request)
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err


@router.get("/items/{item_id}", response_model=FourTierMemoryItemDTO)
async def get_item(
    item_id: str,
    project_hash: str = Query(default="default", description="Project hash partition"),
    service: FourTierFtsService = Depends(get_four_tier_fts_service),
) -> FourTierMemoryItemDTO:
    """Retrieves a single memory item by ID."""
    item = service.get_item(item_id, project_hash=project_hash)
    if item is None:
        raise HTTPException(status_code=404, detail=f"Memory item '{item_id}' not found")
    return item


@router.delete("/items/{item_id}")
async def delete_item(
    item_id: str,
    project_hash: str = Query(default="default", description="Project hash partition"),
    service: FourTierFtsService = Depends(get_four_tier_fts_service),
) -> dict[str, bool | str]:
    """Deletes a memory item by ID."""
    deleted = service.delete_item(item_id, project_hash=project_hash)
    return {"deleted": deleted, "item_id": item_id}


@router.get("/items", response_model=list[FourTierMemoryItemDTO])
async def list_items(
    scope: str | None = Query(default=None, description="Optional scope tier filter"),
    project_hash: str = Query(default="default", description="Project hash partition"),
    session_id: str | None = Query(default=None, description="Optional session ID filter"),
    service: FourTierFtsService = Depends(get_four_tier_fts_service),
) -> list[FourTierMemoryItemDTO]:
    """Lists stored memory items optionally filtered by scope and session ID."""
    try:
        return service.list_items(scope=scope, project_hash=project_hash, session_id=session_id)
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err


@router.get("/search", response_model=list[FtsSearchResultDTO])
async def search_fts(
    query: str = Query(..., min_length=1, description="Full-text query keywords"),
    scope: str | None = Query(default=None, description="Optional scope filter"),
    project_hash: str = Query(default="default", description="Project hash partition"),
    limit: int = Query(default=10, ge=1, le=100, description="Max results"),
    service: FourTierFtsService = Depends(get_four_tier_fts_service),
) -> list[FtsSearchResultDTO]:
    """Executes high-performance SQLite FTS5 BM25 search across memories."""
    try:
        return service.search_fts(query=query, scope=scope, project_hash=project_hash, limit=limit)
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err


@router.post("/dream", response_model=DreamCompactionReportDTO)
async def run_dream_compaction(
    request: RunDreamCompactionRequestDTO,
    service: FourTierFtsService = Depends(get_four_tier_fts_service),
) -> DreamCompactionReportDTO:
    """Triggers background dream compaction merging fragmented notes and pruning stale progress items."""
    try:
        return service.run_dream_compaction(request)
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err
