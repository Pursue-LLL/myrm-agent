"""
[POS] app/api/memory/graph_rrf_router.py
[INPUT] app/schemas/graph_rrf.py, app/services/memory/graph_rrf_service.py
[OUTPUT] router
"""

from __future__ import annotations

from fastapi import APIRouter, status

from app.schemas.graph_rrf import (
    DualChannelSearchRequest,
    DualChannelSearchResponse,
    EntityNodeCreateRequest,
    EntityNodeResponse,
    GraphTraverseRequest,
    GraphTraverseResponse,
)
from app.services.memory.graph_rrf_service import get_graph_rrf_service

router = APIRouter(prefix="/graph-rrf", tags=["memory-graph-rrf"])


@router.post(
    "/nodes",
    response_model=EntityNodeResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create or update knowledge graph entity node",
)
def create_node(req: EntityNodeCreateRequest) -> EntityNodeResponse:
    """Register an entity node into the knowledge graph."""
    service = get_graph_rrf_service()
    return service.add_entity_node(req)


@router.post(
    "/traverse",
    response_model=GraphTraverseResponse,
    summary="Traverse knowledge graph from seed entities",
)
def traverse_graph(req: GraphTraverseRequest) -> GraphTraverseResponse:
    """Execute BFS traversal from seed entities and discover multi-hop associations."""
    service = get_graph_rrf_service()
    return service.traverse_graph(req)


@router.post(
    "/search",
    response_model=DualChannelSearchResponse,
    summary="Dual-channel hybrid vector and knowledge graph RRF search",
)
def search_dual_channel(req: DualChannelSearchRequest) -> DualChannelSearchResponse:
    """Search memories via dual channels (dense vectors + graph topology) fused with RRF."""
    service = get_graph_rrf_service()
    return service.search_dual_channel(req)
