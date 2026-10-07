"""[POS]: app/api/memory/decontamination.py
[INPUT]: HTTP requests for memory provenance vouchers, active threat evaluation, and snapshot rollbacks.
[OUTPUT]: FastAPI APIRouter endpoints managing memory attestation, quarantine barriers, and time-travel rollback.
"""

from fastapi import APIRouter, Depends, HTTPException
from myrm_agent_harness.toolkits.memory import (
    MemoryProvenanceDecontaminationService,
    ProvenanceSourceKind,
)

from app.schemas.decontamination import (
    AttestationResponse,
    CreateSnapshotRequest,
    DecontaminateSessionRequest,
    DecontaminateSessionResponse,
    DecontaminationReportResponse,
    EvaluateMemoryRequest,
    FilterCleanMemoriesRequest,
    FilterCleanMemoriesResponse,
    IssueAttestationRequest,
    QuarantineMemoryRequest,
    RollbackRequest,
    RollbackResponse,
    SnapshotResponse,
)
from app.services.memory.decontamination import get_decontamination_service

router = APIRouter(prefix="/decontamination", tags=["memory_decontamination"])


@router.post("/attest", response_model=AttestationResponse)
def issue_memory_attestation(
    req: IssueAttestationRequest,
    service: MemoryProvenanceDecontaminationService = Depends(get_decontamination_service),
) -> AttestationResponse:
    """Issue a tamper-evident cryptographic provenance attestation for a memory item."""
    source_enum = (
        ProvenanceSourceKind(req.source_kind)
        if req.source_kind in [s.value for s in ProvenanceSourceKind]
        else ProvenanceSourceKind.USER_EXPLICIT_INSTRUCTION
    )
    att = service.issue_attestation(
        memory_id=req.memory_id,
        source_kind=source_enum,
        session_id=req.session_id,
        turn_index=req.turn_index,
        evidence_snippet=req.evidence_snippet,
        author_identity=req.author_identity,
    )
    return AttestationResponse(
        attestation_id=att.attestation_id,
        memory_id=att.memory_id,
        source_kind=att.source_kind.value,
        session_id=att.session_id,
        turn_index=att.turn_index,
        evidence_snippet=att.evidence_snippet,
        author_identity=att.author_identity,
        sha256_signature=att.sha256_signature,
        created_at_epoch=att.created_at_epoch,
    )


@router.get("/attestation/{memory_id}", response_model=AttestationResponse)
def get_memory_attestation(
    memory_id: str,
    service: MemoryProvenanceDecontaminationService = Depends(get_decontamination_service),
) -> AttestationResponse:
    """Retrieve cryptographic origin attestation voucher for a specific memory entry."""
    att = service.get_attestation(memory_id)
    if not att:
        raise HTTPException(status_code=404, detail=f"Attestation for memory '{memory_id}' not found")
    return AttestationResponse(
        attestation_id=att.attestation_id,
        memory_id=att.memory_id,
        source_kind=att.source_kind.value,
        session_id=att.session_id,
        turn_index=att.turn_index,
        evidence_snippet=att.evidence_snippet,
        author_identity=att.author_identity,
        sha256_signature=att.sha256_signature,
        created_at_epoch=att.created_at_epoch,
    )


@router.post("/evaluate", response_model=DecontaminationReportResponse)
def evaluate_memory_content(
    req: EvaluateMemoryRequest,
    service: MemoryProvenanceDecontaminationService = Depends(get_decontamination_service),
) -> DecontaminationReportResponse:
    """Inspect memory text for injection attacks or destructive operations, enforcing quarantine."""
    report = service.evaluate_and_guard(
        memory_id=req.memory_id,
        content=req.content,
        source_kind=req.source_kind,
    )
    return DecontaminationReportResponse(
        memory_id=report.memory_id,
        status=report.status.value,
        threat_reasons=report.threat_reasons,
        evaluated_at_epoch=report.evaluated_at_epoch,
    )


@router.post("/quarantine")
def quarantine_memory(
    req: QuarantineMemoryRequest,
    service: MemoryProvenanceDecontaminationService = Depends(get_decontamination_service),
) -> dict[str, str]:
    """Manually place a suspect memory entry into the quarantine barrier."""
    service.quarantine_memory(memory_id=req.memory_id, reason=req.reason)
    return {"message": f"Memory '{req.memory_id}' placed in quarantine", "status": "quarantined"}


@router.post("/pardon/{memory_id}")
def pardon_memory(
    memory_id: str,
    service: MemoryProvenanceDecontaminationService = Depends(get_decontamination_service),
) -> dict[str, str]:
    """Lift quarantine restriction, returning memory to clean state."""
    service.pardon_memory(memory_id=memory_id)
    return {"message": f"Memory '{memory_id}' pardoned and restored to clean", "status": "clean"}


@router.post("/filter-clean", response_model=FilterCleanMemoriesResponse)
def filter_clean_memories(
    req: FilterCleanMemoriesRequest,
    service: MemoryProvenanceDecontaminationService = Depends(get_decontamination_service),
) -> FilterCleanMemoriesResponse:
    """Screen candidate memory IDs, stripping out any quarantined entries."""
    clean_ids = service.filter_clean_memories(req.memory_ids)
    return FilterCleanMemoriesResponse(clean_memory_ids=clean_ids)


@router.post("/snapshot", response_model=SnapshotResponse)
def create_memory_snapshot(
    req: CreateSnapshotRequest,
    service: MemoryProvenanceDecontaminationService = Depends(get_decontamination_service),
) -> SnapshotResponse:
    """Capture a point-in-time baseline snapshot of currently active memories."""
    snap = service.create_snapshot(label=req.label, active_memory_ids=req.active_memory_ids)
    return SnapshotResponse(
        snapshot_id=snap.snapshot_id,
        label=snap.label,
        memory_ids=snap.memory_ids,
        created_at_epoch=snap.created_at_epoch,
    )


@router.post("/rollback", response_model=RollbackResponse)
def rollback_memory_snapshot(
    req: RollbackRequest,
    service: MemoryProvenanceDecontaminationService = Depends(get_decontamination_service),
) -> RollbackResponse:
    """Rollback memory state to a previous snapshot by quarantining post-snapshot additions."""
    rep = service.rollback_to_snapshot(
        snapshot_id=req.snapshot_id,
        current_memory_ids=req.current_memory_ids,
    )
    return RollbackResponse(
        target_id=rep.target_id,
        label=rep.label,
        quarantined_count=rep.quarantined_count,
        restored_count=rep.restored_count,
        timestamp_epoch=rep.timestamp_epoch,
    )


@router.post("/decontaminate-session", response_model=DecontaminateSessionResponse)
def decontaminate_corrupt_session(
    req: DecontaminateSessionRequest,
    service: MemoryProvenanceDecontaminationService = Depends(get_decontamination_service),
) -> DecontaminateSessionResponse:
    """Trace and quarantine all memories associated with a poisoned conversation session."""
    count = service.decontaminate_session(req.session_id)
    return DecontaminateSessionResponse(session_id=req.session_id, quarantined_count=count)


@router.get("/quarantined")
def list_quarantined_memories(
    limit: int = 50,
    service: MemoryProvenanceDecontaminationService = Depends(get_decontamination_service),
) -> list[dict[str, str | float]]:
    """List currently quarantined memories with violation reasons."""
    return service.list_quarantined(limit=limit)
