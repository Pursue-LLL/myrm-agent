"""FastAPI router for cross-agent composable context, conflict arbitration, and handoff verification.

[INPUT]
- fastapi
- app.schemas.cross_agent_memory::*
- app.services.memory.cross_agent_memory_service::*

[OUTPUT]
- router: APIRouter instance exposing cross-agent memory endpoints

[POS]
API boundary for cross-agent context projection, divergence arbitration, and task handoff integrity.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from app.schemas.cross_agent_memory import (
    ArbitrateConflictRequestDTO,
    ArbitrationOutcomeDTO,
    ComposableContextResponseDTO,
    HandoffPacketDTO,
    HandoffVerificationResponseDTO,
    ProjectComposableContextRequestDTO,
    SealHandoffRequestDTO,
    VerifyHandoffRequestDTO,
)
from app.services.memory.cross_agent_memory_service import (
    CrossAgentMemoryService,
    get_cross_agent_memory_service,
)

router = APIRouter(prefix="/cross-agent", tags=["cross-agent-memory"])


@router.post(
    "/project-context",
    response_model=ComposableContextResponseDTO,
    status_code=status.HTTP_200_OK,
    summary="Project 4-layer composable context isolating private scratchpad",
)
def project_composable_context(
    request: ProjectComposableContextRequestDTO,
    service: CrossAgentMemoryService = Depends(get_cross_agent_memory_service),
) -> ComposableContextResponseDTO:
    """Compose 4-layer virtual reference context preserving 80%+ prefix cache."""
    return service.project_context(request)


@router.post(
    "/arbitrate-conflict",
    response_model=ArbitrationOutcomeDTO,
    status_code=status.HTTP_200_OK,
    summary="Arbitrate memory discrepancy between two agents using 3-tier probe",
)
def arbitrate_memory_conflict(
    request: ArbitrateConflictRequestDTO,
    service: CrossAgentMemoryService = Depends(get_cross_agent_memory_service),
) -> ArbitrationOutcomeDTO:
    """Arbitrate factual conflict using physical ground truth, coordinator authority, or UI escalation."""
    return service.arbitrate_conflict(request)


@router.post(
    "/seal-handoff",
    response_model=HandoffPacketDTO,
    status_code=status.HTTP_200_OK,
    summary="Seal task handoff packet with cryptographic SHA-256 signature",
)
def seal_task_handoff(
    request: SealHandoffRequestDTO,
    service: CrossAgentMemoryService = Depends(get_cross_agent_memory_service),
) -> HandoffPacketDTO:
    """Create a tamper-evident handoff packet for successor agent."""
    return service.seal_handoff(request)


@router.post(
    "/verify-handoff",
    response_model=HandoffVerificationResponseDTO,
    status_code=status.HTTP_200_OK,
    summary="Verify cryptographic seal of incoming task handoff packet",
)
def verify_task_handoff(
    request: VerifyHandoffRequestDTO,
    service: CrossAgentMemoryService = Depends(get_cross_agent_memory_service),
) -> HandoffVerificationResponseDTO:
    """Validate incoming task handoff signature and critical memory assertions."""
    return service.verify_handoff(request)
