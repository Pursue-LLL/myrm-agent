"""
[POS] app/api/security/governed_write_safety_router.py
[INPUT] fastapi, app.schemas.governed_write_safety, app.services.security.governed_write_safety_service
[OUTPUT] governed_write_safety_router
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.schemas.governed_write_safety import (
    ApproveEditRequestDTO,
    ApproveEditResponseDTO,
    CommitEditRequestDTO,
    CommitWriteResultDTO,
    GovernedWriteProposalDTO,
    PreImageSnapshotDTO,
    ProposeEditRequestDTO,
    RegisterOpaqueFileRequestDTO,
    RegisterOpaqueFileResponseDTO,
)
from app.services.security.governed_write_safety_service import (
    GovernedWriteSafetyService,
    get_governed_write_safety_service,
)

router = APIRouter(
    prefix="/governed-write-safety",
    tags=["String-Is-Never-Authority Governed Write Safety"],
)


@router.post(
    "/register",
    response_model=RegisterOpaqueFileResponseDTO,
    summary="Register a raw path behind an opaque file token",
)
def register_opaque_file(
    request: RegisterOpaqueFileRequestDTO,
    service: GovernedWriteSafetyService = Depends(get_governed_write_safety_service),
) -> RegisterOpaqueFileResponseDTO:
    """Register and shield a filesystem path behind a secure opaque token (@file_xxxx)."""
    return service.register_opaque_file(request)


@router.get(
    "/resolve/{opaque_file_id}",
    response_model=RegisterOpaqueFileResponseDTO,
    summary="Resolve an opaque file token to physical filesystem path",
)
def resolve_opaque_file(
    opaque_file_id: str,
    service: GovernedWriteSafetyService = Depends(get_governed_write_safety_service),
) -> RegisterOpaqueFileResponseDTO:
    """Resolve an opaque token back to its physical path within the governance layer."""
    raw_path = service.resolve_path(opaque_file_id)
    if raw_path is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Opaque file ID '{opaque_file_id}' not found",
        )
    return RegisterOpaqueFileResponseDTO(
        opaque_file_id=opaque_file_id,
        raw_path=raw_path,
    )


@router.post(
    "/propose",
    response_model=GovernedWriteProposalDTO,
    summary="Create a governed write proposal bound to base content pre-image",
)
def propose_edit(
    request: ProposeEditRequestDTO,
    service: GovernedWriteSafetyService = Depends(get_governed_write_safety_service),
) -> GovernedWriteProposalDTO:
    """Create a candidate edit proposal bound to base content pre-image hash."""
    try:
        return service.propose_edit(request)
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.post(
    "/approve",
    response_model=ApproveEditResponseDTO,
    summary="Approve a write proposal and issue a single-use write lease token",
)
def approve_edit(
    request: ApproveEditRequestDTO,
    service: GovernedWriteSafetyService = Depends(get_governed_write_safety_service),
) -> ApproveEditResponseDTO:
    """Approve a proposal and issue a single-use write lease token."""
    try:
        return service.approve_edit(request)
    except (KeyError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.post(
    "/commit",
    response_model=CommitWriteResultDTO,
    summary="Commit an approved write proposal with atomic stale check and pre-image capture",
)
def commit_edit(
    request: CommitEditRequestDTO,
    service: GovernedWriteSafetyService = Depends(get_governed_write_safety_service),
) -> CommitWriteResultDTO:
    """Execute atomic write with stale rejection and pre-image snapshot verification."""
    return service.commit_edit(request)


@router.get(
    "/proposal/{proposal_id}",
    response_model=GovernedWriteProposalDTO,
    summary="Get details of a governed write proposal",
)
def get_proposal(
    proposal_id: str,
    service: GovernedWriteSafetyService = Depends(get_governed_write_safety_service),
) -> GovernedWriteProposalDTO:
    """Retrieve governed write proposal by proposal ID."""
    proposal = service.get_proposal(proposal_id)
    if proposal is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Proposal '{proposal_id}' not found",
        )
    return proposal


@router.get(
    "/snapshot/{snapshot_id}",
    response_model=PreImageSnapshotDTO,
    summary="Get pre-image snapshot record",
)
def get_snapshot(
    snapshot_id: str,
    service: GovernedWriteSafetyService = Depends(get_governed_write_safety_service),
) -> PreImageSnapshotDTO:
    """Retrieve pre-image snapshot by snapshot ID."""
    snapshot = service.get_snapshot(snapshot_id)
    if snapshot is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Snapshot '{snapshot_id}' not found",
        )
    return snapshot
