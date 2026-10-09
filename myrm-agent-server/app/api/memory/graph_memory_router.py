"""REST API router for Graph Memory Reorganization and Lineage Traceability.

[POS]
HTTP API endpoints for graph entity node lifecycle, non-destructive evolution,
historical version reversion, lineage audit trails, and graph reorganization.
[INPUT]
- app.schemas.graph_memory: DTO contracts
- app.services.memory.graph_memory_service: Business service layer
[OUTPUT]
- router: FastAPI router mounted under /memory/graph
"""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query, status
from myrm_agent_harness.toolkits.memory import (
    GraphRelationType,
    MemoryGraphEdge,
    MemoryGraphNode,
    MemoryLineageTrail,
)

from app.schemas.graph_memory import (
    CreateEdgeRequest,
    CreateNodeRequest,
    EvolveNodeRequest,
    GraphRelationTypeEnum,
    LineageStepDTO,
    MemoryGraphEdgeDTO,
    MemoryGraphNodeDTO,
    MemoryLineageTrailDTO,
    MemoryNodeStatusEnum,
    ReorganizeRequest,
    ReorganizeResponse,
    RevertNodeRequest,
)
from app.services.memory.graph_memory_service import (
    GraphMemoryService,
    get_graph_memory_service,
)

router = APIRouter(prefix="/graph", tags=["memory-graph"])


def _to_node_dto(node: MemoryGraphNode) -> MemoryGraphNodeDTO:
    return MemoryGraphNodeDTO(
        node_id=node.node_id,
        lineage_root_id=node.lineage_root_id,
        version=node.version,
        subject=node.subject,
        predicate=node.predicate,
        object_value=node.object_value,
        content=node.content,
        confidence=node.confidence,
        status=MemoryNodeStatusEnum(node.status.value),
        created_at=node.created_at,
        updated_at=node.updated_at,
        source_session_id=node.source_session_id,
        evidence_quote=node.evidence_quote,
        metadata=dict(node.metadata),
    )


def _to_edge_dto(edge: MemoryGraphEdge) -> MemoryGraphEdgeDTO:
    return MemoryGraphEdgeDTO(
        edge_id=edge.edge_id,
        source_node_id=edge.source_node_id,
        target_node_id=edge.target_node_id,
        relation_type=GraphRelationTypeEnum(edge.relation_type.value),
        weight=edge.weight,
        rationale=edge.rationale,
        created_at=edge.created_at,
    )


def _to_trail_dto(trail: MemoryLineageTrail) -> MemoryLineageTrailDTO:
    return MemoryLineageTrailDTO(
        target_node=_to_node_dto(trail.target_node),
        lineage_root_id=trail.lineage_root_id,
        ancestor_nodes=[_to_node_dto(n) for n in trail.ancestor_nodes],
        descendant_nodes=[_to_node_dto(n) for n in trail.descendant_nodes],
        steps=[
            LineageStepDTO(
                step_index=s.step_index,
                node=_to_node_dto(s.node),
                relation_to_target=(
                    GraphRelationTypeEnum(s.relation_to_target.value)
                    if s.relation_to_target is not None
                    else None
                ),
                rationale=s.rationale,
                timestamp=s.timestamp,
            )
            for s in trail.steps
        ],
        relation_edges=[_to_edge_dto(e) for e in trail.relation_edges],
        depth=trail.depth,
        is_latest=trail.is_latest,
    )


@router.post(
    "/nodes",
    response_model=MemoryGraphNodeDTO,
    status_code=status.HTTP_201_CREATED,
    summary="Create initial memory graph node",
)
def create_node(
    payload: CreateNodeRequest,
) -> MemoryGraphNodeDTO:
    """Create a new initial entity node in the memory graph."""
    svc: GraphMemoryService = get_graph_memory_service()
    node = svc.create_node(
        subject=payload.subject,
        predicate=payload.predicate,
        object_value=payload.object_value,
        content=payload.content,
        confidence=payload.confidence,
        source_session_id=payload.source_session_id,
        evidence_quote=payload.evidence_quote,
        metadata=payload.metadata,
    )
    return _to_node_dto(node)


@router.get(
    "/nodes",
    response_model=List[MemoryGraphNodeDTO],
    summary="List memory graph nodes",
)
def list_nodes(
    subject: Optional[str] = Query(None, description="Filter by subject entity"),
    active_only: bool = Query(False, description="Filter to active nodes only"),
) -> List[MemoryGraphNodeDTO]:
    """Retrieve nodes matching the supplied filters."""
    svc: GraphMemoryService = get_graph_memory_service()
    nodes = svc.list_nodes(
        subject=subject,
        active_only=active_only,
    )
    return [_to_node_dto(n) for n in nodes]


@router.get(
    "/nodes/{node_id}",
    response_model=MemoryGraphNodeDTO,
    summary="Get single memory graph node",
)
def get_node(node_id: str) -> MemoryGraphNodeDTO:
    """Retrieve a specific graph node by identifier."""
    svc: GraphMemoryService = get_graph_memory_service()
    node = svc.get_node(node_id)
    if node is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Node '{node_id}' not found",
        )
    return _to_node_dto(node)


@router.post(
    "/nodes/{node_id}/evolve",
    response_model=MemoryGraphNodeDTO,
    summary="Evolve node into superseding version",
)
def evolve_node(
    node_id: str,
    payload: EvolveNodeRequest,
) -> MemoryGraphNodeDTO:
    """Evolve node non-destructively, deprecating the old node and incrementing version."""
    svc: GraphMemoryService = get_graph_memory_service()
    try:
        _, new_node, _ = svc.evolve_node(
            node_id=node_id,
            object_value=payload.object_value,
            content=payload.content,
            rationale=payload.rationale,
            metadata=payload.metadata,
        )
        return _to_node_dto(new_node)
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.post(
    "/nodes/{node_id}/revert",
    response_model=MemoryGraphNodeDTO,
    summary="Revert node to target historical version",
)
def revert_node(
    node_id: str,
    payload: RevertNodeRequest,
) -> MemoryGraphNodeDTO:
    """Non-destructively revert memory to a specified prior version snapshot."""
    svc: GraphMemoryService = get_graph_memory_service()
    try:
        _, new_version_node = svc.revert_node(
            historical_node_id=payload.historical_node_id,
            rationale=payload.rationale,
        )
        return _to_node_dto(new_version_node)
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.get(
    "/nodes/{node_id}/lineage",
    response_model=MemoryLineageTrailDTO,
    summary="Get full lineage audit trail for node",
)
def get_lineage(node_id: str) -> MemoryLineageTrailDTO:
    """Trace all historical mutation steps and relations for this node entity."""
    svc: GraphMemoryService = get_graph_memory_service()
    try:
        trail = svc.get_lineage(node_id)
        return _to_trail_dto(trail)
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.post(
    "/edges",
    response_model=MemoryGraphEdgeDTO,
    status_code=status.HTTP_201_CREATED,
    summary="Create semantic relationship edge",
)
def create_edge(
    payload: CreateEdgeRequest,
) -> MemoryGraphEdgeDTO:
    """Establish a semantic edge between two existing nodes."""
    svc: GraphMemoryService = get_graph_memory_service()
    try:
        edge = svc.add_edge(
            source_node_id=payload.source_node_id,
            target_node_id=payload.target_node_id,
            relation_type=GraphRelationType(payload.relation_type.value),
            weight=payload.weight,
            rationale=payload.rationale,
        )
        return _to_edge_dto(edge)
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.get(
    "/edges",
    response_model=List[MemoryGraphEdgeDTO],
    summary="List semantic edges",
)
def list_edges(
    source_node_id: Optional[str] = Query(None, description="Filter by source node ID"),
    target_node_id: Optional[str] = Query(None, description="Filter by target node ID"),
    relation_type: Optional[GraphRelationTypeEnum] = Query(
        None, description="Filter by relation type"
    ),
) -> List[MemoryGraphEdgeDTO]:
    """Query semantic edges with optional endpoints or relation filtering."""
    svc: GraphMemoryService = get_graph_memory_service()
    domain_rel = (
        GraphRelationType(relation_type.value) if relation_type is not None else None
    )
    edges = svc.list_edges(
        source_node_id=source_node_id,
        target_node_id=target_node_id,
        relation_type=domain_rel,
    )
    return [_to_edge_dto(e) for e in edges]


@router.post(
    "/reorganize",
    response_model=ReorganizeResponse,
    summary="Trigger holistic graph reorganization",
)
def reorganize_graph(
    payload: ReorganizeRequest,
) -> ReorganizeResponse:
    """Run semantic graph clustering, relation inference, and conflict resolution."""
    svc: GraphMemoryService = get_graph_memory_service()
    report = svc.reorganize(
        min_confidence=payload.min_confidence,
    )
    return ReorganizeResponse(
        batch_id=report.batch_id,
        analyzed_nodes_count=report.analyzed_nodes_count,
        created_edges_count=report.created_edges_count,
        superseded_nodes_count=report.superseded_nodes_count,
        deductions_count=report.deductions_count,
        edges=[_to_edge_dto(e) for e in report.edges],
        created_at=report.created_at,
    )
