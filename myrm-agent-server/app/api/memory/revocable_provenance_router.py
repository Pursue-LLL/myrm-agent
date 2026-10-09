"""[POS]: app/api/memory/revocable_provenance_router.py
[INPUT]: FastAPI APIRouter, Depends, Query, Path, HTTPException, and revocable provenance schemas.
[OUTPUT]: API router exposing endpoints for provenance memory tracking, atomic revocation, and dream diaries.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from app.schemas.revocable_provenance import (
    DreamDiaryEntryDTO,
    ForgetMemoryRequestDTO,
    ForgetResultDTO,
    ProvenanceQualifiedMemoryDTO,
    RecordDreamDiaryRequestDTO,
    SaveProvenanceMemoryRequestDTO,
)
from app.services.memory.revocable_provenance_service import (
    RevocableProvenanceService,
    get_revocable_provenance_service,
)

router = APIRouter(prefix="/provenance", tags=["memory-revocable-provenance"])


@router.post("/memories", response_model=ProvenanceQualifiedMemoryDTO)
async def save_memory(
    request: SaveProvenanceMemoryRequestDTO,
    service: RevocableProvenanceService = Depends(get_revocable_provenance_service),
) -> ProvenanceQualifiedMemoryDTO:
    """Saves a new long-term memory with strict origin conversation turn provenance."""
    try:
        return service.save_memory(request)
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err


@router.get("/memories/{memory_id}", response_model=ProvenanceQualifiedMemoryDTO)
async def get_memory(
    memory_id: str,
    service: RevocableProvenanceService = Depends(get_revocable_provenance_service),
) -> ProvenanceQualifiedMemoryDTO:
    """Retrieves a single memory entry along with full provenance origin metadata."""
    mem = service.get_memory(memory_id)
    if mem is None:
        raise HTTPException(status_code=404, detail=f"Memory '{memory_id}' not found")
    return mem


@router.get("/memories", response_model=list[ProvenanceQualifiedMemoryDTO])
async def list_memories(
    include_revoked: bool = Query(default=False, description="Whether to include revoked entries"),
    service: RevocableProvenanceService = Depends(get_revocable_provenance_service),
) -> list[ProvenanceQualifiedMemoryDTO]:
    """Lists all stored memories, optionally filtering out revoked ones."""
    return service.list_memories(include_revoked=include_revoked)


@router.get("/memories/session/{session_id}", response_model=list[ProvenanceQualifiedMemoryDTO])
async def find_by_session(
    session_id: str,
    include_revoked: bool = Query(default=False, description="Whether to include revoked entries"),
    service: RevocableProvenanceService = Depends(get_revocable_provenance_service),
) -> list[ProvenanceQualifiedMemoryDTO]:
    """Finds all memories derived from a specific source chat session."""
    return service.find_by_session(session_id=session_id, include_revoked=include_revoked)


@router.get("/memories/message/{message_id}", response_model=list[ProvenanceQualifiedMemoryDTO])
async def find_by_message(
    message_id: str,
    include_revoked: bool = Query(default=False, description="Whether to include revoked entries"),
    service: RevocableProvenanceService = Depends(get_revocable_provenance_service),
) -> list[ProvenanceQualifiedMemoryDTO]:
    """Finds memories originating from a specific message turn."""
    return service.find_by_message(message_id=message_id, include_revoked=include_revoked)


@router.delete("/memories/{memory_id}/forget", response_model=ForgetResultDTO)
async def forget_memory(
    memory_id: str,
    reason: str = Query(default="", description="Reason or correction note for revocation"),
    service: RevocableProvenanceService = Depends(get_revocable_provenance_service),
) -> ForgetResultDTO:
    """Atomically revokes a memory, registering a tombstone to prevent zombie resurfacing."""
    request = ForgetMemoryRequestDTO(reason=reason)
    return service.forget_memory(memory_id=memory_id, request=request)


@router.post("/dream-diaries", response_model=DreamDiaryEntryDTO)
async def record_dream_diary(
    request: RecordDreamDiaryRequestDTO,
    service: RevocableProvenanceService = Depends(get_revocable_provenance_service),
) -> DreamDiaryEntryDTO:
    """Logs a completed background dreaming memory consolidation cycle."""
    return service.record_dream_diary(request)


@router.get("/dream-diaries", response_model=list[DreamDiaryEntryDTO])
async def list_dream_diaries(
    agent_id: str | None = Query(default=None, description="Optional agent filter"),
    limit: int = Query(default=50, ge=1, le=200, description="Max entries to return"),
    service: RevocableProvenanceService = Depends(get_revocable_provenance_service),
) -> list[DreamDiaryEntryDTO]:
    """Lists recorded dream diaries in reverse chronological order."""
    return service.list_dream_diaries(agent_id=agent_id, limit=limit)
