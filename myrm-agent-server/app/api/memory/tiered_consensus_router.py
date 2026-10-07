# [POS]: app/api/memory/tiered_consensus_router.py
# [INPUT]: app.schemas.tiered_consensus, app.services.memory.tiered_consensus_service
# [OUTPUT]: router (FastAPI APIRouter for Tiered Memory Hierarchy & Proposed Consensus Flow)

"""FastAPI router for Tiered Memory Hierarchy and Proposed Consensus Flow Suite (Item 114)."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from app.schemas.tiered_consensus import (
    ConsensusAuditLogDTO,
    ProposeRecordRequest,
    ReviewProposalRequest,
    RevokeConsensusRequest,
    TieredMemoryRecordDTO,
)
from app.services.memory.tiered_consensus_service import (
    TieredConsensusService,
    get_tiered_consensus_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tiered-consensus", tags=["Tiered Consensus"])


@router.post(
    "/propose",
    response_model=TieredMemoryRecordDTO,
    status_code=201,
    summary="Propose or persist a scoped tiered memory record",
)
async def propose_record(
    request: ProposeRecordRequest,
    service: Annotated[TieredConsensusService, Depends(get_tiered_consensus_service)],
) -> TieredMemoryRecordDTO:
    """Propose a new memory guideline with tier scoping (Personal, Project, or Team Consensus)."""
    try:
        return service.propose_record(request)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get(
    "/records",
    response_model=list[TieredMemoryRecordDTO],
    summary="Query tiered memory records with scoping and status filtering",
)
async def query_records(
    service: Annotated[TieredConsensusService, Depends(get_tiered_consensus_service)],
    scope_tier: str | None = Query(default=None, description="Scope tier: personal, project, team_consensus"),
    status: str | None = Query(default=None, description="Lifecycle status: proposed, approved, rejected, revoked"),
    project_id: str | None = Query(default=None, description="Project workspace ID filter"),
    owner_peer_id: str | None = Query(default=None, description="Originating peer ID filter"),
    include_proposed: bool = Query(default=False, description="Whether to include unapproved team proposals"),
) -> list[TieredMemoryRecordDTO]:
    """Retrieve memory records with default safety filtering hiding unapproved draft propositions."""
    return service.query_records(
        scope_tier=scope_tier,
        status=status,
        project_id=project_id,
        owner_peer_id=owner_peer_id,
        include_proposed=include_proposed,
    )


@router.get(
    "/records/{record_id}",
    response_model=TieredMemoryRecordDTO,
    summary="Get single tiered memory record",
)
async def get_record(
    record_id: str,
    service: Annotated[TieredConsensusService, Depends(get_tiered_consensus_service)],
) -> TieredMemoryRecordDTO:
    """Retrieve a single memory record by its identifier, or 404 if not found."""
    record = service.get_record(record_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"Memory record '{record_id}' not found.")
    return record


@router.post(
    "/records/{record_id}/approve",
    response_model=TieredMemoryRecordDTO,
    summary="Approve draft proposal to active consensus",
)
async def approve_proposal(
    record_id: str,
    request: ReviewProposalRequest,
    service: Annotated[TieredConsensusService, Depends(get_tiered_consensus_service)],
) -> TieredMemoryRecordDTO:
    """Explicitly approve and promote a proposed draft to active team consensus."""
    try:
        return service.approve_proposal(record_id, request)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post(
    "/records/{record_id}/reject",
    response_model=TieredMemoryRecordDTO,
    summary="Reject unverified draft proposal",
)
async def reject_proposal(
    record_id: str,
    request: ReviewProposalRequest,
    service: Annotated[TieredConsensusService, Depends(get_tiered_consensus_service)],
) -> TieredMemoryRecordDTO:
    """Reject and retire an unverified proposed consensus draft."""
    try:
        return service.reject_proposal(record_id, request)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.post(
    "/records/{record_id}/revoke",
    response_model=TieredMemoryRecordDTO,
    summary="Revoke previously active consensus guideline",
)
async def revoke_consensus(
    record_id: str,
    request: RevokeConsensusRequest,
    service: Annotated[TieredConsensusService, Depends(get_tiered_consensus_service)],
) -> TieredMemoryRecordDTO:
    """Revoke an active consensus rule with optional supersession linking."""
    try:
        return service.revoke_consensus(record_id, request)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.get(
    "/records/{record_id}/audits",
    response_model=list[ConsensusAuditLogDTO],
    summary="Get lifecycle transition audit trail for record",
)
async def get_audit_trail(
    record_id: str,
    service: Annotated[TieredConsensusService, Depends(get_tiered_consensus_service)],
) -> list[ConsensusAuditLogDTO]:
    """Retrieve immutable lifecycle audit log entries for a target record."""
    return service.get_audit_trail(record_id)
