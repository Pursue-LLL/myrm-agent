"""
[POS] app/api/memory/experience_gene_router.py
[INPUT] app/schemas/experience_gene.py, app/services/memory/experience_gene_service.py
[OUTPUT] router
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.schemas.experience_gene import (
    ExperienceGeneResponse,
    ExtractGeneRequest,
    ExtractGeneResponse,
    GeneAdviceListResponse,
    GeneAdviceRequest,
    GeneLedgerStatsResponse,
    GenePenalizeRequest,
)
from app.services.memory.experience_gene_service import (
    ExperienceGeneService,
    get_experience_gene_service,
)

router = APIRouter(prefix="/evolution/genes", tags=["experience_genes"])


@router.post(
    "/extract",
    response_model=ExtractGeneResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Extract and record causal experience gene from multi-turn trace",
)
def extract_and_record_gene(
    request: ExtractGeneRequest,
    service: ExperienceGeneService = Depends(get_experience_gene_service),
) -> ExtractGeneResponse:
    """Extract causal signals, refuted hypotheses, and proven resolutions from a task trace."""
    return service.extract_and_record(request)


@router.post(
    "/advice",
    response_model=GeneAdviceListResponse,
    summary="Get planning-stage mutation advice matching active signals",
)
def get_mutation_advice(
    request: GeneAdviceRequest,
    service: ExperienceGeneService = Depends(get_experience_gene_service),
) -> GeneAdviceListResponse:
    """Retrieve actionable advice to preempt dead-ends and steer towards verified resolutions."""
    return service.get_mutation_advice(request)


@router.post(
    "/penalize",
    response_model=ExperienceGeneResponse,
    summary="Apply negative feedback penalty to an ineffective gene",
)
def penalize_gene(
    request: GenePenalizeRequest,
    service: ExperienceGeneService = Depends(get_experience_gene_service),
) -> ExperienceGeneResponse:
    """Decrement confidence score when a gene guidance path fails during runtime."""
    updated = service.penalize_gene(request)
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Gene not found: {request.gene_id}",
        )
    return updated


@router.get(
    "/list",
    response_model=list[ExperienceGeneResponse],
    summary="List all recorded experience genes",
)
def list_genes(
    service: ExperienceGeneService = Depends(get_experience_gene_service),
) -> list[ExperienceGeneResponse]:
    """List all tracked experience genes ordered by proof count."""
    return service.list_genes()


@router.get(
    "/stats",
    response_model=GeneLedgerStatsResponse,
    summary="Get experience gene evolution ledger statistics",
)
def get_stats(
    service: ExperienceGeneService = Depends(get_experience_gene_service),
) -> GeneLedgerStatsResponse:
    """Get aggregate metrics including total genes, proof count, and average confidence."""
    return service.get_stats()
