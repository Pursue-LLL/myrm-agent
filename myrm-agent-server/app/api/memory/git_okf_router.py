"""REST endpoints for Git-native OKF v0.2 bundle loading, search, validation, and progressive disclosure.

[POS]
app/api/memory/git_okf_router.py

[INPUT]
- FastAPI APIRouter, Depends, Query, Path, and GitOKF DTOs

[OUTPUT]
- REST endpoints for Git-native OKF v0.2 bundle loading, search, validation, and progressive disclosure
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.schemas.git_okf import (
    ConceptSummaryItemDTO,
    LoadBundleRequestDTO,
    LoadBundleResponseDTO,
    OKFConceptDetailDTO,
    OKFDisclosureSummaryDTO,
    OKFSearchRequestDTO,
    OKFSearchResultDTO,
    OKFValidationReportDTO,
)
from app.services.memory.git_okf_service import GitOKFService, get_git_okf_service

router = APIRouter(prefix="/git-okf", tags=["git-okf-memory"])


@router.post("/bundle/load", response_model=LoadBundleResponseDTO)
def load_bundle(
    payload: LoadBundleRequestDTO,
    service: GitOKFService = Depends(get_git_okf_service),
) -> LoadBundleResponseDTO:
    """Load and index an OKF v0.2 knowledge bundle from the filesystem."""
    try:
        count, path = service.load_bundle(payload.bundle_path)
        return LoadBundleResponseDTO(
            bundle_path=path,
            loaded_concepts_count=count,
            is_success=True,
        )
    except FileNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        ) from e


@router.post("/concepts/search", response_model=list[OKFSearchResultDTO])
def search_concepts(
    payload: OKFSearchRequestDTO,
    service: GitOKFService = Depends(get_git_okf_service),
) -> list[OKFSearchResultDTO]:
    """Execute sub-millisecond in-memory BM25 lexical search over active concepts."""
    results = service.search_concepts(
        query=payload.query,
        limit=payload.limit,
        filter_governance=payload.filter_governance,
        filter_status=payload.filter_status,
    )
    return [
        OKFSearchResultDTO(
            concept_id=r.concept_id,
            title=r.title,
            type=r.type,
            description=r.description,
            governance=r.governance,
            score=r.score,
            matched_fields=r.matched_fields,
            tags=r.tags,
            code_refs=r.code_refs,
            is_stale=r.is_stale,
        )
        for r in results
    ]


@router.post("/validate", response_model=OKFValidationReportDTO)
def validate_bundle(
    service: GitOKFService = Depends(get_git_okf_service),
) -> OKFValidationReportDTO:
    """Run full OKF v0.2 conformance, memory rot, and anti-tamper trust audit."""
    report = service.validate_bundle()
    return OKFValidationReportDTO(
        bundle_path=report.bundle_path,
        declared_version=report.declared_version,
        concept_count=report.concept_count,
        errors=report.errors,
        warnings=report.warnings,
        gate_findings=report.gate_findings,
        stale_count=report.stale_count,
        superseded_trust_count=report.superseded_trust_count,
        is_conformant=report.is_conformant,
        gate_passed=report.gate_passed,
    )


@router.get("/disclosure/summary", response_model=OKFDisclosureSummaryDTO)
def get_disclosure_summary(
    service: GitOKFService = Depends(get_git_okf_service),
) -> OKFDisclosureSummaryDTO:
    """Get first-phase lightweight progressive disclosure card (<300 tokens footprint)."""
    summary = service.get_disclosure_summary()
    return OKFDisclosureSummaryDTO(
        bundle_path=summary.bundle_path,
        total_concepts=summary.total_concepts,
        stale_count=summary.stale_count,
        concepts=[
            ConceptSummaryItemDTO(
                id=c.id,
                title=c.title,
                description=c.description,
                governance=c.governance,
                status=c.status,
                is_stale=c.is_stale,
                code_refs=c.code_refs,
            )
            for c in summary.concepts
        ],
    )


@router.get("/concepts/{concept_id:path}", response_model=OKFConceptDetailDTO)
def get_concept_detail(
    concept_id: str,
    service: GitOKFService = Depends(get_git_okf_service),
) -> OKFConceptDetailDTO:
    """Fetch complete concept markdown content and metadata for phase-two deep inspection."""
    c = service.get_concept_detail(concept_id)
    if not c:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Concept '{concept_id}' not found in active bundle",
        )
    val_report = service.validate_bundle()
    is_stale = any(
        f"{c.id}: concept is stale" in w for w in val_report.warnings
    )
    return OKFConceptDetailDTO(
        id=c.id,
        path=c.path,
        type=c.type,
        title=c.title,
        description=c.description,
        governance=c.effective_governance().value,
        status=c.status.value,
        stale_after=c.stale_after,
        code_refs=c.code_refs,
        tags=c.tags,
        body=c.body,
        is_stale=is_stale,
    )
