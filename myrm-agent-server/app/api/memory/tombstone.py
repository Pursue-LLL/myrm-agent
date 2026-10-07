"""[POS]: app/api/memory/tombstone.py
[INPUT]: FastAPI HTTP requests for memory contradiction curation, tombstone masking, and eviction.
[OUTPUT]: Strongly-typed JSON responses confirming contradiction reports and tombstone lifecycle state.
"""

from fastapi import APIRouter, Depends
from myrm_agent_harness.toolkits.memory import (
    MemoryTombstoneCurationService,
    TombstoneCandidateItem,
)

from app.schemas.tombstone import (
    ContradictionPairDTO,
    EvictTombstonesRequest,
    EvictTombstonesResponse,
    FilterActiveRequest,
    FilterActiveResponse,
    ListRecordsResponse,
    ReviveTombstoneRequest,
    ReviveTombstoneResponse,
    ScanCurateRequest,
    ScanCurateResponse,
    TombstoneCandidateDTO,
    TombstoneRecordDTO,
)
from app.services.memory.tombstone import get_tombstone_curation_service

router = APIRouter(prefix="/tombstone", tags=["memory-tombstone"])


def _to_candidate_item(dto: TombstoneCandidateDTO) -> TombstoneCandidateItem:
    return TombstoneCandidateItem(
        memory_id=dto.memory_id,
        content=dto.content,
        category=dto.category,
        created_at=dto.created_at,
        tags=dto.tags,
    )


def _to_candidate_dto(item: TombstoneCandidateItem) -> TombstoneCandidateDTO:
    return TombstoneCandidateDTO(
        memory_id=item.memory_id,
        content=item.content,
        category=item.category,
        created_at=item.created_at,
        tags=item.tags,
    )


@router.post("/scan-curate", response_model=ScanCurateResponse)
def scan_and_curate_memories(
    request: ScanCurateRequest,
    service: MemoryTombstoneCurationService = Depends(get_tombstone_curation_service),
) -> ScanCurateResponse:
    """Scan candidate memories for antithetical contradictions and apply tombstone isolation."""
    items = [_to_candidate_item(dto) for dto in request.memories]
    report = service.curate_and_tombstone(items, auto_tombstone=request.auto_tombstone)

    contradictions_dto = [
        ContradictionPairDTO(
            new_memory_id=c.new_memory_id,
            outdated_memory_id=c.outdated_memory_id,
            topic_keyword=c.topic_keyword,
            confidence_score=c.confidence_score,
            reason=c.reason,
        )
        for c in report.contradictions
    ]

    return ScanCurateResponse(
        total_scanned=report.total_scanned,
        total_contradictions_found=report.total_contradictions_found,
        total_tombstoned=report.total_tombstoned,
        total_evicted=report.total_evicted,
        contradictions=contradictions_dto,
        timestamp=report.timestamp,
    )


@router.post("/filter-active", response_model=FilterActiveResponse)
def filter_active_memories(
    request: FilterActiveRequest,
    service: MemoryTombstoneCurationService = Depends(get_tombstone_curation_service),
) -> FilterActiveResponse:
    """Screen candidate memories against active tombstone barriers to prevent prompt contamination."""
    items = [_to_candidate_item(dto) for dto in request.candidates]
    active_items = service.filter_active_memories(items)
    dtos = [_to_candidate_dto(it) for it in active_items]

    return FilterActiveResponse(
        total_active=len(dtos),
        active_memories=dtos,
    )


@router.post("/revive", response_model=ReviveTombstoneResponse)
def revive_tombstone(
    request: ReviveTombstoneRequest,
    service: MemoryTombstoneCurationService = Depends(get_tombstone_curation_service),
) -> ReviveTombstoneResponse:
    """Reinstate a tombstoned memory item back to active recall pool upon user intervention."""
    success = service.revive_tombstone(request.memory_id)
    msg = (
        f"Memory directive {request.memory_id} successfully revived."
        if success
        else f"Memory directive {request.memory_id} was not in tombstoned state or not found."
    )
    return ReviveTombstoneResponse(
        success=success,
        memory_id=request.memory_id,
        message=msg,
    )


@router.post("/evict", response_model=EvictTombstonesResponse)
def evict_tombstones(
    request: EvictTombstonesRequest,
    service: MemoryTombstoneCurationService = Depends(get_tombstone_curation_service),
) -> EvictTombstonesResponse:
    """Physically evict tombstoned entries after retention expiration or explicit confirmation."""
    evicted_count = service.evict_tombstones(request.memory_ids)
    return EvictTombstonesResponse(
        evicted_count=evicted_count,
        message=f"Successfully evicted {evicted_count} tombstoned memory directives.",
    )


@router.get("/records", response_model=ListRecordsResponse)
def list_curation_records(
    service: MemoryTombstoneCurationService = Depends(get_tombstone_curation_service),
) -> ListRecordsResponse:
    """List all tombstone audit records for UI panel display."""
    records = service.list_curation_records()
    dtos = [
        TombstoneRecordDTO(
            memory_id=r.memory_id,
            state=r.state.value,
            tombstoned_at=r.tombstoned_at,
            superseded_by_id=r.superseded_by_id,
            reason=r.reason,
            evicted_at=r.evicted_at,
        )
        for r in records
    ]
    return ListRecordsResponse(
        total_records=len(dtos),
        records=dtos,
    )
