"""
[POS] app/api/memory/self_verification_router.py
[INPUT] fastapi, app.schemas.memory_self_verification, app.services.memory.memory_self_verification_service
[OUTPUT] router

FastAPI router exposing endpoints for Memory Self-Verification Diagnostic Suite & Fact Update Benchmark.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from app.schemas.memory_self_verification import (
    FactMutationProbeRequestDTO,
    FactMutationProbeResponseDTO,
    ProceduralAntiDropProbeRequestDTO,
    ProceduralAntiDropProbeResponseDTO,
    RunDiagnosticSuiteRequestDTO,
    RunDiagnosticSuiteResponseDTO,
    ZeroLexicalProbeRequestDTO,
    ZeroLexicalProbeResponseDTO,
)
from app.services.memory.memory_self_verification_service import (
    MemorySelfVerificationService,
    get_memory_self_verification_service,
)

router = APIRouter()


@router.post(
    "/self-verification/run",
    response_model=RunDiagnosticSuiteResponseDTO,
    status_code=status.HTTP_200_OK,
    summary="Execute comprehensive 4-dimensional memory diagnostic suite inside isolated sandbox",
)
def run_diagnostic_suite(
    request: RunDiagnosticSuiteRequestDTO,
    service: MemorySelfVerificationService = Depends(get_memory_self_verification_service),
) -> RunDiagnosticSuiteResponseDTO:
    """Run full suite (mutation, zero-lexical, procedural) and guarantee physical sandbox rollback cleanup."""
    return service.run_full_diagnostic_suite(request)


@router.post(
    "/self-verification/fact-mutation",
    response_model=FactMutationProbeResponseDTO,
    status_code=status.HTTP_200_OK,
    summary="Execute in-place fact mutation probe asserting conflict elimination",
)
def run_fact_mutation_probe(
    request: FactMutationProbeRequestDTO,
    service: MemorySelfVerificationService = Depends(get_memory_self_verification_service),
) -> FactMutationProbeResponseDTO:
    """Assert that updating a fact in-place leaves exactly 1 fresh record and zero contradictions."""
    return service.run_fact_mutation_probe(request)


@router.post(
    "/self-verification/zero-lexical",
    response_model=ZeroLexicalProbeResponseDTO,
    status_code=status.HTTP_200_OK,
    summary="Execute pure semantic recall probe with zero lexical surface overlap",
)
def run_zero_lexical_probe(
    request: ZeroLexicalProbeRequestDTO,
    service: MemorySelfVerificationService = Depends(get_memory_self_verification_service),
) -> ZeroLexicalProbeResponseDTO:
    """Assert that recall succeeds when query and memory share zero word bag overlap (pure vector semantic)."""
    return service.run_zero_lexical_probe(request)


@router.post(
    "/self-verification/procedural-anti-drop",
    response_model=ProceduralAntiDropProbeResponseDTO,
    status_code=status.HTTP_200_OK,
    summary="Execute procedural routing and anti-silent-drop verification probe",
)
def run_procedural_anti_drop_probe(
    request: ProceduralAntiDropProbeRequestDTO,
    service: MemorySelfVerificationService = Depends(get_memory_self_verification_service),
) -> ProceduralAntiDropProbeResponseDTO:
    """Verify that operational troubleshooting rules are routed to procedural track and never dropped."""
    return service.run_procedural_anti_drop_probe(request)
