"""REST API router for Multi-Human Multi-Agent Live Document Co-Authoring Ledger."""

from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.schemas.coauthoring_ledger import (
    AcceptProposalRequest,
    AcquireLeaseRequest,
    ApplyDeltaRequest,
    ArbitrateConflictRequest,
    ArbitrationVerdictDTO,
    CollaboratorProfileDTO,
    ConflictRecordDTO,
    DeltaEntryDTO,
    DocumentBlockDTO,
    InitDocumentRequest,
    RegisterCollaboratorRequest,
    ReleaseLeaseRequest,
    StagingProposalDTO,
)
from app.services.agent.coauthoring_ledger_service import (
    CoAuthoringLedgerService,
    get_coauthoring_ledger_service,
)

router = APIRouter(
    prefix="/chats/{chat_id}/coauthoring-ledger",
    tags=["Live Document Co-Authoring Ledger"],
)


@router.post("/collaborators", response_model=CollaboratorProfileDTO, status_code=status.HTTP_201_CREATED)
async def register_collaborator(
    chat_id: str,
    req: RegisterCollaboratorRequest,
    service: CoAuthoringLedgerService = Depends(get_coauthoring_ledger_service),
) -> CollaboratorProfileDTO:
    """Register human participant or AI agent in tripartite space."""
    return service.register_collaborator(chat_id, req)


@router.get("/collaborators", response_model=List[CollaboratorProfileDTO])
async def list_collaborators(
    chat_id: str,
    service: CoAuthoringLedgerService = Depends(get_coauthoring_ledger_service),
) -> List[CollaboratorProfileDTO]:
    """List all registered collaborators."""
    return service.list_collaborators(chat_id)


@router.post("/document/init", response_model=List[DocumentBlockDTO])
async def init_document(
    chat_id: str,
    req: InitDocumentRequest,
    service: CoAuthoringLedgerService = Depends(get_coauthoring_ledger_service),
) -> List[DocumentBlockDTO]:
    """Initialize live document with blocks."""
    return service.init_document(chat_id, req)


@router.get("/blocks", response_model=List[DocumentBlockDTO])
async def list_blocks(
    chat_id: str,
    service: CoAuthoringLedgerService = Depends(get_coauthoring_ledger_service),
) -> List[DocumentBlockDTO]:
    """List all ordered blocks in live document."""
    return service.list_blocks(chat_id)


@router.get("/markdown")
async def render_markdown(
    chat_id: str,
    service: CoAuthoringLedgerService = Depends(get_coauthoring_ledger_service),
) -> Dict[str, str]:
    """Render full markdown document."""
    md = service.render_markdown(chat_id)
    return {"markdown": md}


@router.post("/leases/acquire")
async def acquire_lease(
    chat_id: str,
    req: AcquireLeaseRequest,
    service: CoAuthoringLedgerService = Depends(get_coauthoring_ledger_service),
) -> Dict[str, bool]:
    """Acquire lease lock on a block."""
    ok = service.acquire_lease(chat_id, req)
    return {"acquired": ok}


@router.post("/leases/release")
async def release_lease(
    chat_id: str,
    req: ReleaseLeaseRequest,
    service: CoAuthoringLedgerService = Depends(get_coauthoring_ledger_service),
) -> Dict[str, bool]:
    """Release lease lock on a block."""
    ok = service.release_lease(chat_id, req)
    return {"released": ok}


@router.post("/deltas", response_model=DocumentBlockDTO)
async def apply_delta(
    chat_id: str,
    req: ApplyDeltaRequest,
    service: CoAuthoringLedgerService = Depends(get_coauthoring_ledger_service),
) -> DocumentBlockDTO:
    """Apply atomic delta mutation to document block."""
    try:
        return service.apply_delta(chat_id, req)
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_423_LOCKED, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/deltas", response_model=List[DeltaEntryDTO])
async def get_deltas(
    chat_id: str,
    block_id: Optional[str] = Query(None),
    author_id: Optional[str] = Query(None),
    service: CoAuthoringLedgerService = Depends(get_coauthoring_ledger_service),
) -> List[DeltaEntryDTO]:
    """Query immutable delta ledger entries."""
    return service.get_deltas(chat_id, block_id=block_id, author_id=author_id)


@router.get("/contributions")
async def get_contributions(
    chat_id: str,
    service: CoAuthoringLedgerService = Depends(get_coauthoring_ledger_service),
) -> Dict[str, int]:
    """Get contribution counts per author."""
    return service.get_contributions(chat_id)


@router.post("/arbitrate", response_model=ArbitrationVerdictDTO)
async def arbitrate_conflict(
    chat_id: str,
    req: ArbitrateConflictRequest,
    service: CoAuthoringLedgerService = Depends(get_coauthoring_ledger_service),
) -> ArbitrationVerdictDTO:
    """Arbitrate competing updates between humans and AI agents."""
    return service.arbitrate_conflict(chat_id, req)


@router.get("/proposals", response_model=List[StagingProposalDTO])
async def list_proposals(
    chat_id: str,
    block_id: Optional[str] = Query(None),
    service: CoAuthoringLedgerService = Depends(get_coauthoring_ledger_service),
) -> List[StagingProposalDTO]:
    """List isolated staging proposals."""
    return service.list_proposals(chat_id, block_id=block_id)


@router.post("/proposals/{proposal_id}/accept", response_model=StagingProposalDTO)
async def accept_proposal(
    chat_id: str,
    proposal_id: str,
    req: AcceptProposalRequest,
    service: CoAuthoringLedgerService = Depends(get_coauthoring_ledger_service),
) -> StagingProposalDTO:
    """Accept and merge isolated staging proposal into active document block."""
    prop = service.accept_proposal(chat_id, proposal_id=proposal_id, reviewer_id=req.reviewer_id)
    if not prop:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Proposal {proposal_id} not found",
        )
    return prop


@router.get("/conflicts", response_model=List[ConflictRecordDTO])
async def list_conflicts(
    chat_id: str,
    service: CoAuthoringLedgerService = Depends(get_coauthoring_ledger_service),
) -> List[ConflictRecordDTO]:
    """List historical conflict records."""
    return service.list_conflicts(chat_id)


@router.post("/reset")
async def reset_session(
    chat_id: str,
    service: CoAuthoringLedgerService = Depends(get_coauthoring_ledger_service),
) -> Dict[str, bool]:
    """Reset coauthoring ledger session."""
    service.reset_session(chat_id)
    return {"reset": True}
