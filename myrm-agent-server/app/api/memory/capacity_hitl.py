"""[POS]: app/api/memory/capacity_hitl.py
[INPUT]: FastAPI HTTP requests for capacity inspection, candidate generation, and HITL decision resolution.
[OUTPUT]: Strongly-typed JSON responses conforming to capacity HITL API contracts.
"""

from fastapi import APIRouter, Depends, HTTPException
from myrm_agent_harness.toolkits.memory import (
    CapacityHitlService,
    HitlCandidateProposal,
    HitlCandidateStatus,
)

from app.schemas.capacity_hitl import (
    ArchivedEntriesResponse,
    ArchivedEntryDTO,
    CapacityStatusResponse,
    GenerateCandidatesRequest,
    GenerateCandidatesResponse,
    HitlCandidateDTO,
    MemoryEntryRefDTO,
    ResolveCandidateRequest,
    ResolveCandidateResponse,
)
from app.services.memory.capacity_hitl import get_capacity_hitl_service

router = APIRouter(prefix="/capacity-hitl", tags=["memory-capacity-hitl"])


def _to_proposal_dto(prop: HitlCandidateProposal) -> HitlCandidateDTO:
    entries = [
        MemoryEntryRefDTO(
            id=e.id,
            content=e.content,
            content_hash=e.content_hash,
            tags=e.tags,
            created_at=e.created_at,
            access_count=e.access_count,
        )
        for e in prop.source_entries
    ]
    return HitlCandidateDTO(
        candidate_id=prop.candidate_id,
        action_kind=prop.action_kind.value,
        source_entries=entries,
        proposed_content=prop.proposed_content,
        reason=prop.reason,
        confidence=prop.confidence,
        status=prop.status.value,
        created_at=prop.created_at,
        resolved_at=prop.resolved_at,
        reviewer_note=prop.reviewer_note,
    )


@router.get("/status", response_model=CapacityStatusResponse)
def get_capacity_status(
    total_entries: int = 0,
    max_entries: int | None = None,
    service: CapacityHitlService = Depends(get_capacity_hitl_service),
) -> CapacityStatusResponse:
    """Inspect current memory capacity utilization against ladder alert thresholds."""
    report = service.check_capacity_status(
        total_entries=total_entries, max_entries=max_entries
    )
    return CapacityStatusResponse(
        total_entries=report.total_entries,
        max_entries=report.max_entries,
        capacity_ratio=report.capacity_ratio,
        alert_level=report.alert_level.value,
        pending_candidate_count=report.pending_candidate_count,
        timestamp=report.timestamp,
    )


@router.post("/propose-candidates", response_model=GenerateCandidatesResponse)
def propose_candidates(
    request: GenerateCandidatesRequest,
    service: CapacityHitlService = Depends(get_capacity_hitl_service),
) -> GenerateCandidatesResponse:
    """Analyze memory bank entries and formulate read-only merge/archive proposals."""
    proposals = service.generate_and_store_proposals(
        entries=request.entries,
        max_entries=request.max_entries,
        max_proposals=request.max_proposals,
    )
    return GenerateCandidatesResponse(
        total_proposals=len(proposals),
        proposals=[_to_proposal_dto(p) for p in proposals],
    )


@router.get("/candidates", response_model=list[HitlCandidateDTO])
def list_candidates(
    status: str | None = None,
    service: CapacityHitlService = Depends(get_capacity_hitl_service),
) -> list[HitlCandidateDTO]:
    """List stored HITL proposals, optionally filtered by status."""
    target_status: HitlCandidateStatus | None = None
    if status is not None:
        try:
            target_status = HitlCandidateStatus(status)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid status: {status}. Must be one of {[s.value for s in HitlCandidateStatus]}",
            ) from None

    proposals = service.list_proposals(status=target_status)
    return [_to_proposal_dto(p) for p in proposals]


@router.post(
    "/candidates/{candidate_id}/resolve", response_model=ResolveCandidateResponse
)
def resolve_candidate(
    candidate_id: str,
    request: ResolveCandidateRequest,
    service: CapacityHitlService = Depends(get_capacity_hitl_service),
) -> ResolveCandidateResponse:
    """Resolve a candidate proposal with human approval or rejection and CAS concurrency check."""
    try:
        decision = HitlCandidateStatus(request.decision)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid decision: {request.decision}. Must be 'approved' or 'rejected'",
        ) from None

    if decision not in (HitlCandidateStatus.APPROVED, HitlCandidateStatus.REJECTED):
        raise HTTPException(
            status_code=400,
            detail="Resolution decision must be either 'approved' or 'rejected'",
        )

    success, msg, resolved = service.resolve_candidate(
        candidate_id=candidate_id,
        decision=decision,
        reviewer_note=request.reviewer_note,
        current_entry_hashes=request.current_entry_hashes,
    )

    if not success and resolved is None and "not found" in msg.lower():
        raise HTTPException(status_code=404, detail=msg)

    dto = _to_proposal_dto(resolved) if resolved else None
    return ResolveCandidateResponse(
        success=success,
        message=msg,
        proposal=dto,
    )


@router.get("/archived", response_model=ArchivedEntriesResponse)
def list_archived_entries(
    service: CapacityHitlService = Depends(get_capacity_hitl_service),
) -> ArchivedEntriesResponse:
    """Retrieve history of entries safely preserved in cold archive storage."""
    archived = service.list_archived_entries()
    dtos = [
        ArchivedEntryDTO(
            id=str(a["id"]),
            content=str(a["content"]),
            tags=str(a["tags"]),
            archived_at=float(a["archived_at"]),
            origin_candidate_id=str(a["origin_candidate_id"]),
        )
        for a in archived
    ]
    return ArchivedEntriesResponse(total_count=len(dtos), archived_entries=dtos)
