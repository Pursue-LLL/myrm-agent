"""[POS]: app/api/memory/temporal_graph_router.py
[INPUT]: FastAPI APIRouter, Depends, HTTPException, Query, and temporal graph schemas.
[OUTPUT]: API router exposing endpoints for temporal entity nodes, fact edge conflict resolution, lineage, and decay query.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from app.schemas.temporal_graph import (
    FactConflictResolutionResultDTO,
    SaveEntityNodeRequestDTO,
    SaveFactEdgeRequestDTO,
    TemporalEntityNodeDTO,
    TemporalFactEdgeDTO,
    TemporalFactHitDTO,
    TemporalGraphStatsDTO,
)
from app.services.memory.temporal_graph_service import (
    TemporalGraphService,
    get_temporal_graph_service,
)

router = APIRouter(prefix="/temporal-graph", tags=["memory-temporal-graph"])


@router.post("/nodes", response_model=TemporalEntityNodeDTO)
async def save_node(
    request: SaveEntityNodeRequestDTO,
    service: TemporalGraphService = Depends(get_temporal_graph_service),
) -> TemporalEntityNodeDTO:
    """Saves or updates an entity node in the temporal knowledge graph."""
    try:
        return service.save_node(request)
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err


@router.get("/nodes/{node_id}", response_model=TemporalEntityNodeDTO)
async def get_node(
    node_id: str,
    service: TemporalGraphService = Depends(get_temporal_graph_service),
) -> TemporalEntityNodeDTO:
    """Retrieves an entity node by ID."""
    node = service.get_node(node_id)
    if node is None:
        raise HTTPException(status_code=404, detail=f"Entity node '{node_id}' not found")
    return node


@router.get("/nodes", response_model=list[TemporalEntityNodeDTO])
async def list_nodes(
    entity_type: str | None = Query(default=None, description="Optional entity type filter"),
    limit: int = Query(default=100, ge=1, le=500, description="Max nodes to return"),
    service: TemporalGraphService = Depends(get_temporal_graph_service),
) -> list[TemporalEntityNodeDTO]:
    """Lists entity nodes optionally filtered by classification type."""
    return service.list_nodes(entity_type=entity_type, limit=limit)


@router.delete("/nodes/{node_id}")
async def delete_node(
    node_id: str,
    service: TemporalGraphService = Depends(get_temporal_graph_service),
) -> dict[str, bool | str]:
    """Deletes an entity node and cascades removal of associated edges."""
    deleted = service.delete_node(node_id)
    return {"deleted": deleted, "node_id": node_id}


@router.post("/edges", response_model=FactConflictResolutionResultDTO)
async def save_fact_edge(
    request: SaveFactEdgeRequestDTO,
    service: TemporalGraphService = Depends(get_temporal_graph_service),
) -> FactConflictResolutionResultDTO:
    """Inserts a relationship fact edge, automatically reconciling mutual exclusion conflicts."""
    try:
        return service.save_fact_edge_with_reconciliation(request)
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err


@router.get("/edges/{edge_id}", response_model=TemporalFactEdgeDTO)
async def get_edge(
    edge_id: str,
    service: TemporalGraphService = Depends(get_temporal_graph_service),
) -> TemporalFactEdgeDTO:
    """Retrieves a relationship edge by ID."""
    edge = service.get_edge(edge_id)
    if edge is None:
        raise HTTPException(status_code=404, detail=f"Fact edge '{edge_id}' not found")
    return edge


@router.get("/edges", response_model=list[TemporalFactEdgeDTO])
async def list_edges(
    predicate: str | None = Query(default=None, description="Optional predicate filter"),
    active_only: bool = Query(default=True, description="Filter out superseded edges"),
    limit: int = Query(default=100, ge=1, le=500, description="Max edges to return"),
    service: TemporalGraphService = Depends(get_temporal_graph_service),
) -> list[TemporalFactEdgeDTO]:
    """Lists fact edges with optional filtering."""
    return service.list_edges(predicate=predicate, active_only=active_only, limit=limit)


@router.get("/edges/{edge_id}/lineage", response_model=list[TemporalFactEdgeDTO])
async def get_lineage(
    edge_id: str,
    service: TemporalGraphService = Depends(get_temporal_graph_service),
) -> list[TemporalFactEdgeDTO]:
    """Traces the backward lineage chain of superseded historical edges."""
    return service.get_lineage(edge_id)


@router.get("/facts/search", response_model=list[TemporalFactHitDTO])
@router.get("/query", response_model=list[TemporalFactHitDTO])
async def query_facts(
    source_id: str | None = Query(default=None, description="Optional source entity filter"),
    predicate: str | None = Query(default=None, description="Optional predicate filter"),
    active_only: bool = Query(default=True, description="Whether to exclude superseded facts"),
    limit: int = Query(default=50, ge=1, le=200, description="Max results"),
    service: TemporalGraphService = Depends(get_temporal_graph_service),
) -> list[TemporalFactHitDTO]:
    """Queries temporal fact edges ranked by dynamic half-life decay score."""
    return service.query_temporal_facts(
        source_id=source_id,
        predicate=predicate,
        active_only=active_only,
        limit=limit,
    )


@router.get("/stats", response_model=TemporalGraphStatsDTO)
async def get_stats(
    service: TemporalGraphService = Depends(get_temporal_graph_service),
) -> TemporalGraphStatsDTO:
    """Computes summary metrics and average recency decay score for the graph."""
    return service.get_stats()
