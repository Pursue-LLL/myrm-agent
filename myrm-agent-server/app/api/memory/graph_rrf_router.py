"""
[POS] app/api/memory/graph_rrf_router.py
[INPUT] app/schemas/graph_rrf.py, app/services/memory/graph_rrf_service.py
[OUTPUT] router
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.schemas.graph_rrf import (
    DualChannelSearchRequest,
    DualChannelSearchResponse,
    EntityNodeCreateRequest,
    EntityNodeResponse,
    GraphTraverseRequest,
    GraphTraverseResponse,
    MemoryAssociationRequest,
    RelationEdgeCreateRequest,
    RelationEdgeResponse,
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


@router.get(
    "/nodes/{node_id}",
    response_model=EntityNodeResponse,
    summary="Get entity node by ID",
)
def get_node(node_id: str) -> EntityNodeResponse:
    """Retrieve an entity node by its unique identifier."""
    service = get_graph_rrf_service()
    node = service.get_entity_node(node_id)
    if not node:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Entity node '{node_id}' not found",
        )
    return node


@router.post(
    "/edges",
    response_model=RelationEdgeResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create or update knowledge graph relationship edge",
)
def create_edge(req: RelationEdgeCreateRequest) -> RelationEdgeResponse:
    """Register a relationship edge between two entity nodes."""
    service = get_graph_rrf_service()
    return service.add_relation_edge(req)


@router.post(
    "/associate",
    status_code=status.HTTP_200_OK,
    summary="Associate memory unit with an entity node",
)
def associate_memory(req: MemoryAssociationRequest) -> dict[str, str]:
    """Associate a long-term memory unit with a knowledge graph entity node."""
    service = get_graph_rrf_service()
    service.associate_memory(req)
    return {"status": "success", "memory_id": req.memory_id, "entity_id": req.entity_id}


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
