"""REST API router for Conclusion Attribution & Chat Evidence.

[POS]
Provides HTTP endpoints for attributed conclusions declaration, causality traversal,
anti-cycle defense, and on-demand verifiable chat evidence retrieval.

[INPUT]
- fastapi
- app.schemas.conclusion_evidence
- app.services.memory.conclusion_evidence.provider

[OUTPUT]
- router (FastAPI APIRouter)
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status
from myrm_agent_harness.toolkits.memory import DerivationCycleError

from app.schemas.conclusion_evidence import (
    AttributedConclusionDTO,
    ChatWithEvidenceRequestDTO,
    ChatWithEvidenceResponseDTO,
    ConclusionEvidenceStatsDTO,
    CreateAttributedConclusionDTO,
    DerivationTraversalViewDTO,
)
from app.services.memory.conclusion_evidence.provider import (
    execute_chat_with_evidence,
    execute_create_conclusion,
    get_evidence_stats,
    query_conclusion,
    query_derivatives,
    query_premises,
    query_two_way_traversal,
)

router = APIRouter(prefix="/conclusion-evidence", tags=["Conclusion Attribution & Evidence"])


@router.post(
    "/conclusions",
    response_model=AttributedConclusionDTO,
    status_code=status.HTTP_200_OK,
    summary="Declare an attributed conclusion",
)
def create_conclusion(req: CreateAttributedConclusionDTO) -> AttributedConclusionDTO:
    """Register an attributed conclusion in the DAG with cycle defense."""
    try:
        return execute_create_conclusion(req)
    except DerivationCycleError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.get(
    "/conclusions/{conclusion_id}",
    response_model=AttributedConclusionDTO,
    status_code=status.HTTP_200_OK,
    summary="Get single attributed conclusion",
)
def get_conclusion(conclusion_id: str) -> AttributedConclusionDTO:
    """Retrieve an attributed conclusion by ID."""
    result = query_conclusion(conclusion_id)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conclusion '{conclusion_id}' not found",
        )
    return result


@router.get(
    "/conclusions/{conclusion_id}/derivatives",
    response_model=list[AttributedConclusionDTO],
    status_code=status.HTTP_200_OK,
    summary="Get downstream conclusions derived from this conclusion",
)
def get_derivatives(
    conclusion_id: str,
    max_depth: int = Query(default=5, ge=1, le=20),
) -> list[AttributedConclusionDTO]:
    """Traverse downstream to inspect cascade derivative conclusions."""
    return query_derivatives(conclusion_id, max_depth=max_depth)


@router.get(
    "/conclusions/{conclusion_id}/premises",
    response_model=list[AttributedConclusionDTO],
    status_code=status.HTTP_200_OK,
    summary="Get upstream premise conclusions supporting this conclusion",
)
def get_premises(
    conclusion_id: str,
    max_depth: int = Query(default=5, ge=1, le=20),
) -> list[AttributedConclusionDTO]:
    """Traverse upstream premises supporting this deduction."""
    return query_premises(conclusion_id, max_depth=max_depth)


@router.get(
    "/conclusions/{conclusion_id}/traversal",
    response_model=DerivationTraversalViewDTO,
    status_code=status.HTTP_200_OK,
    summary="Get two-way causal derivation view",
)
def get_traversal(
    conclusion_id: str,
    max_depth: int = Query(default=5, ge=1, le=20),
) -> DerivationTraversalViewDTO:
    """Retrieve comprehensive two-way causality graph view."""
    return query_two_way_traversal(conclusion_id, max_depth=max_depth)


@router.post(
    "/chat-with-evidence",
    response_model=ChatWithEvidenceResponseDTO,
    status_code=status.HTTP_200_OK,
    summary="Query conclusions with optional verifiable evidence packaging",
)
def chat_with_evidence_endpoint(
    req: ChatWithEvidenceRequestDTO,
) -> ChatWithEvidenceResponseDTO:
    """Perform memory reasoning query with on-demand evidence bundle."""
    return execute_chat_with_evidence(req)


@router.get(
    "/stats",
    response_model=ConclusionEvidenceStatsDTO,
    status_code=status.HTTP_200_OK,
    summary="Get conclusion derivation graph statistics",
)
def get_stats() -> ConclusionEvidenceStatsDTO:
    """Retrieve causality graph topology statistics."""
    return get_evidence_stats()
