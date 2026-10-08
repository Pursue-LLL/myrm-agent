"""API Router for Conclusion Attribution and Chat Evidence Suite (Item 141).

Exposes REST and MCP-aligned endpoints for causal memory creation,
bidirectional graph traversal, ripple impact analysis, and audit-ready evidence packaging.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status

from app.schemas.conclusion_attribution import (
    AttributionMetricsResponse,
    ChatWithEvidenceRequest,
    ChatWithEvidenceResponse,
    CreateConclusionRequest,
    CreateConclusionResponse,
    DeleteConclusionResponse,
    ListConclusionsResponse,
    QueryConclusionsRequest,
    QueryConclusionsResponse,
    RippleImpactResponse,
    TraverseTreeResponse,
)
from app.services.memory.conclusion_attribution.provider import (
    ConclusionAttributionProvider,
)

router = APIRouter(prefix="/api/memory/attribution", tags=["Conclusion Attribution"])


def _get_provider() -> ConclusionAttributionProvider:
    return ConclusionAttributionProvider.get_instance()


@router.post(
    "/conclusions",
    response_model=CreateConclusionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create attributed memory conclusion",
)
def create_conclusion(payload: CreateConclusionRequest) -> CreateConclusionResponse:
    provider = _get_provider()
    try:
        dto = provider.create_conclusion(
            peer_id=payload.peer_id,
            content=payload.content,
            level=payload.level,
            source_ids=payload.source_ids,
            session_id=payload.session_id,
            confidence=payload.confidence,
            metadata=payload.metadata,
        )
        return CreateConclusionResponse(conclusion=dto, status="created")
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e


@router.get(
    "/conclusions",
    response_model=ListConclusionsResponse,
    summary="List memory conclusions (paginated)",
)
def list_conclusions(
    peer_id: str | None = Query(default=None, description="Filter by peer identifier"),
    session_id: str | None = Query(default=None, description="Filter by session identifier"),
    level: str | None = Query(default=None, description="Filter by level: explicit/deductive/inductive"),
    reverse: bool = Query(default=False, description="Oldest first if True"),
    page: int = Query(default=1, ge=1, description="Page number 1-indexed"),
    size: int = Query(default=50, ge=1, le=100, description="Items per page"),
) -> ListConclusionsResponse:
    provider = _get_provider()
    items, total = provider.list_conclusions(
        peer_id=peer_id,
        session_id=session_id,
        level=level,
        reverse=reverse,
        page=page,
        size=size,
    )
    return ListConclusionsResponse(items=items, total=total, page=page, size=size)


@router.post(
    "/query",
    response_model=QueryConclusionsResponse,
    summary="Semantic query for attributed conclusions",
)
def query_conclusions(payload: QueryConclusionsRequest) -> QueryConclusionsResponse:
    provider = _get_provider()
    items = provider.query_conclusions(
        query=payload.query,
        peer_id=payload.peer_id,
        level=payload.level,
        top_k=payload.top_k,
    )
    return QueryConclusionsResponse(items=items, total=len(items))


@router.get(
    "/tree/downward/{conclusion_id}",
    response_model=TraverseTreeResponse,
    summary="Walk downwards from conclusion to explicit premises",
)
def walk_downward_tree(
    conclusion_id: str,
    max_depth: int = Query(default=15, ge=1, le=30),
) -> TraverseTreeResponse:
    provider = _get_provider()
    nodes = provider.walk_downward(conclusion_id=conclusion_id, max_depth=max_depth)
    if not nodes:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conclusion not found or has no premises: {conclusion_id}",
        )
    return TraverseTreeResponse(
        root_id=conclusion_id,
        direction="downward",
        nodes=nodes,
        total_nodes=len(nodes),
    )


@router.get(
    "/tree/upward/{conclusion_id}",
    response_model=TraverseTreeResponse,
    summary="Walk upwards from premise to derived conclusions",
)
def walk_upward_tree(
    conclusion_id: str,
    max_depth: int = Query(default=15, ge=1, le=30),
) -> TraverseTreeResponse:
    provider = _get_provider()
    nodes = provider.walk_upward(premise_id=conclusion_id, max_depth=max_depth)
    if not nodes:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Premise not found or has no derived children: {conclusion_id}",
        )
    return TraverseTreeResponse(
        root_id=conclusion_id,
        direction="upward",
        nodes=nodes,
        total_nodes=len(nodes),
    )


@router.get(
    "/impact/{conclusion_id}",
    response_model=RippleImpactResponse,
    summary="Evaluate ripple impact before modifying or deleting conclusion",
)
def get_ripple_impact(conclusion_id: str) -> RippleImpactResponse:
    provider = _get_provider()
    return provider.get_ripple_impact(conclusion_id=conclusion_id)


@router.delete(
    "/conclusions/{conclusion_id}",
    response_model=DeleteConclusionResponse,
    summary="Delete conclusion with optional subtree cascade",
)
def delete_conclusion(
    conclusion_id: str,
    cascade: bool = Query(default=False, description="Cascade delete all derived conclusions"),
) -> DeleteConclusionResponse:
    provider = _get_provider()
    deleted_ids = provider.delete_conclusion(conclusion_id=conclusion_id, cascade=cascade)
    if not deleted_ids:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conclusion not found: {conclusion_id}",
        )
    return DeleteConclusionResponse(
        deleted_ids=deleted_ids,
        cascade=cascade,
        status="deleted",
    )


@router.post(
    "/chat",
    response_model=ChatWithEvidenceResponse,
    summary="Chat endpoint returning transparent grounding evidence package",
)
def chat_with_evidence(payload: ChatWithEvidenceRequest) -> ChatWithEvidenceResponse:
    provider = _get_provider()
    reply, evidence = provider.chat_with_evidence(
        query=payload.query,
        peer_id=payload.peer_id,
        session_id=payload.session_id,
        include_evidence=payload.include_evidence,
    )
    return ChatWithEvidenceResponse(reply=reply, evidence=evidence)


@router.get(
    "/stats",
    response_model=AttributionMetricsResponse,
    summary="Get memory attribution telemetry and health metrics",
)
def get_attribution_stats(
    peer_id: str | None = Query(default=None, description="Optional peer filter"),
) -> AttributionMetricsResponse:
    provider = _get_provider()
    return provider.get_metrics(peer_id=peer_id)
