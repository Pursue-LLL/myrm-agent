"""REST API router for Natural Language Memory Feedback and Live Correction Suite.

[POS]
HTTP API endpoints for in-conversation correction detection, conflict localization,
atomic memory state mutation, and natural language acknowledgement delivery.
[INPUT]
- app.schemas.live_correction: DTO contracts
- app.services.memory.live_correction_service: Business service layer
[OUTPUT]
- router: FastAPI router mounted under /memory/live-correction
"""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, HTTPException, status
from myrm_agent_harness.toolkits.memory import (
    CorrectionAckReceipt,
    LiveCorrectionMutationResult,
    TargetNodeCandidate,
)

from app.schemas.live_correction import (
    CorrectionAckReceiptDTO,
    CorrectionIntentKindEnum,
    CorrectionSlotDTO,
    LiveCorrectionHistoryResponse,
    LiveCorrectionMutationResultDTO,
    LiveCorrectionStatusResponse,
    MutationActionEnum,
    ProcessUtteranceRequest,
    SeedCandidateRequest,
    TargetNodeCandidateDTO,
)
from app.services.memory.live_correction_service import (
    LiveCorrectionService,
    get_live_correction_service,
)

router = APIRouter(prefix="/live-correction", tags=["memory-live-correction"])


def _to_candidate_dto(candidate: TargetNodeCandidate) -> TargetNodeCandidateDTO:
    return TargetNodeCandidateDTO(
        memory_id=candidate.memory_id,
        content=candidate.content,
        cube_id=candidate.cube_id,
        match_score=candidate.match_score,
        attributes=dict(candidate.attributes),
    )


def _to_mutation_dto(
    mutation: LiveCorrectionMutationResult,
) -> LiveCorrectionMutationResultDTO:
    return LiveCorrectionMutationResultDTO(
        action=MutationActionEnum(mutation.action.value),
        target_memory_id=mutation.target_memory_id,
        new_memory_id=mutation.new_memory_id,
        status=mutation.status,
        superseded_content=mutation.superseded_content,
        new_content=mutation.new_content,
        audit_trail=dict(mutation.audit_trail),
        timestamp=mutation.timestamp,
    )


def _to_receipt_dto(receipt: CorrectionAckReceipt) -> CorrectionAckReceiptDTO:
    return CorrectionAckReceiptDTO(
        success=receipt.success,
        ack_message=receipt.ack_message,
        intent=CorrectionIntentKindEnum(receipt.intent.value),
        slot=CorrectionSlotDTO(
            corrected_value=receipt.slot.corrected_value,
            negated_value=receipt.slot.negated_value,
            subject=receipt.slot.subject,
            intent=CorrectionIntentKindEnum(receipt.slot.intent.value),
            confidence=receipt.slot.confidence,
            raw_utterance=receipt.slot.raw_utterance,
        ),
        mutated_record=(
            _to_mutation_dto(receipt.mutated_record)
            if receipt.mutated_record is not None
            else None
        ),
        processing_ms=receipt.processing_ms,
    )


@router.post(
    "/process",
    response_model=CorrectionAckReceiptDTO,
    summary="Process conversational utterance for live correction",
)
def process_utterance(
    request: ProcessUtteranceRequest,
) -> CorrectionAckReceiptDTO:
    """Scan utterance for natural language memory feedback, localize target, and execute mutation."""
    service: LiveCorrectionService = get_live_correction_service()

    candidates = None
    if request.candidates is not None:
        candidates = [
            TargetNodeCandidate(
                memory_id=c.memory_id,
                content=c.content,
                cube_id=c.cube_id,
                match_score=c.match_score,
                attributes=c.attributes,
            )
            for c in request.candidates
        ]

    receipt = service.process_utterance(
        utterance=request.utterance,
        candidates=candidates,
    )

    if receipt is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No memory correction intent detected in provided utterance",
        )

    return _to_receipt_dto(receipt)


@router.get(
    "/candidates",
    response_model=List[TargetNodeCandidateDTO],
    summary="List active candidate memory items",
)
def list_candidates() -> List[TargetNodeCandidateDTO]:
    """Retrieve all current candidates available for conflict localization."""
    service: LiveCorrectionService = get_live_correction_service()
    return [_to_candidate_dto(c) for c in service.list_candidates()]


@router.post(
    "/candidates",
    response_model=TargetNodeCandidateDTO,
    status_code=status.HTTP_201_CREATED,
    summary="Seed or register a candidate memory node",
)
def seed_candidate(
    request: SeedCandidateRequest,
) -> TargetNodeCandidateDTO:
    """Add a new memory node candidate to the active pool."""
    service: LiveCorrectionService = get_live_correction_service()
    added = service.add_candidate(
        memory_id=request.memory_id,
        content=request.content,
        cube_id=request.cube_id,
        attributes=request.attributes,
    )
    return _to_candidate_dto(added)


@router.get(
    "/history",
    response_model=LiveCorrectionHistoryResponse,
    summary="Get execution history of live corrections",
)
def get_history() -> LiveCorrectionHistoryResponse:
    """Retrieve all live memory mutations performed during the session."""
    service: LiveCorrectionService = get_live_correction_service()
    history = service.get_history()
    return LiveCorrectionHistoryResponse(
        history=[_to_mutation_dto(m) for m in history],
        total=len(history),
    )


@router.get(
    "/status",
    response_model=LiveCorrectionStatusResponse,
    summary="Get health and operational status of live correction engine",
)
def get_status() -> LiveCorrectionStatusResponse:
    """Return health metrics, active candidate count, and total mutations count."""
    service: LiveCorrectionService = get_live_correction_service()
    return LiveCorrectionStatusResponse(
        service_status="ready",
        candidates_count=len(service.list_candidates()),
        mutations_count=len(service.get_history()),
    )


@router.post(
    "/reset",
    response_model=LiveCorrectionStatusResponse,
    summary="Reset candidate pool and history to initial default demo seeds",
)
def reset_pool() -> LiveCorrectionStatusResponse:
    """Clear and reseed initial candidates for pristine testing."""
    service: LiveCorrectionService = get_live_correction_service()
    service.clear_all()
    service.seed_default_candidates()
    return LiveCorrectionStatusResponse(
        service_status="reset_completed",
        candidates_count=len(service.list_candidates()),
        mutations_count=0,
    )
