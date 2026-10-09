"""FastAPI router for memory skill triad and physical scope isolation.

[POS]
HTTP boundary for physical scope partition derivation, visible provider degradation
inspection, machine CLI envelope wrapping, and repository integration pipeline verification.

[INPUT]
- fastapi::APIRouter, Depends, status
- app.schemas.skill_triad
- app.services.memory.skill_triad

[OUTPUT]
- router (FastAPI APIRouter)
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.schemas.skill_triad import (
    CliEnvelopeResponse,
    DegradedReportResponse,
    DeleteScopeRequest,
    DeleteScopeResponse,
    FormatCliEnvelopeRequest,
    ProviderAssessRequest,
    ResolveScopeRequest,
    ScopePartitionResponse,
    SkillTriadHealthResponse,
    ValidateSurveyRequest,
    ValidateSurveyResponse,
    VerifySeamsRequest,
    VerifySeamsResponse,
)
from app.services.memory.skill_triad import (
    MemorySkillTriadProvider,
    get_memory_skill_triad_provider,
)

router = APIRouter(prefix="/skill-triad", tags=["Memory Skill Triad & Scope Isolation"])


@router.post(
    "/scope/resolve",
    response_model=ScopePartitionResponse,
    status_code=status.HTTP_200_OK,
    summary="Resolve deterministic physical directory and dedicated SQLite database path",
)
async def resolve_scope_partition(
    request: ResolveScopeRequest,
    provider: Annotated[
        MemorySkillTriadProvider,
        Depends(get_memory_skill_triad_provider),
    ],
) -> ScopePartitionResponse:
    """Computes length-prefixed namespace hash and resolves physical storage path."""
    return provider.resolve_scope(request)


@router.post(
    "/scope/delete",
    response_model=DeleteScopeResponse,
    status_code=status.HTTP_200_OK,
    summary="Atomically purge physical directory for a specific scope",
)
async def delete_scope_partition(
    request: DeleteScopeRequest,
    provider: Annotated[
        MemorySkillTriadProvider,
        Depends(get_memory_skill_triad_provider),
    ],
) -> DeleteScopeResponse:
    """Removes physical scope directory and SQLite file, ensuring zero lingering state."""
    return provider.delete_scope(request)


@router.post(
    "/provider/assess",
    response_model=DegradedReportResponse,
    status_code=status.HTTP_200_OK,
    summary="Assess provider availability and visible degradation status",
)
async def assess_providers(
    request: ProviderAssessRequest,
    provider: Annotated[
        MemorySkillTriadProvider,
        Depends(get_memory_skill_triad_provider),
    ],
) -> DegradedReportResponse:
    """Inspects provider configuration and returns fallback diagnostics."""
    return provider.assess_providers(request)


@router.post(
    "/cli/envelope",
    response_model=CliEnvelopeResponse,
    status_code=status.HTTP_200_OK,
    summary="Format memory operation into standardized machine CLI envelope",
)
async def format_cli_envelope(
    request: FormatCliEnvelopeRequest,
    provider: Annotated[
        MemorySkillTriadProvider,
        Depends(get_memory_skill_triad_provider),
    ],
) -> CliEnvelopeResponse:
    """Wraps result into JSON envelope with duration and auto-confirmed flag for agent loops."""
    return provider.format_cli_envelope(request)


@router.post(
    "/pipeline/survey",
    response_model=ValidateSurveyResponse,
    status_code=status.HTTP_200_OK,
    summary="Validate 4-question pre-integration repository survey findings",
)
async def validate_pipeline_survey(
    request: ValidateSurveyRequest,
    provider: Annotated[
        MemorySkillTriadProvider,
        Depends(get_memory_skill_triad_provider),
    ],
) -> ValidateSurveyResponse:
    """Validates prompt assembly site, identity binding, installed provider, and write hook."""
    return provider.validate_survey(request)


@router.post(
    "/pipeline/verify",
    response_model=VerifySeamsResponse,
    status_code=status.HTTP_200_OK,
    summary="Verify read/write integration seams and roundtrip test status",
)
async def verify_pipeline_seams(
    request: VerifySeamsRequest,
    provider: Annotated[
        MemorySkillTriadProvider,
        Depends(get_memory_skill_triad_provider),
    ],
) -> VerifySeamsResponse:
    """Ensures token-budgeted prompt injection and post-turn persistence seams are verified."""
    return provider.verify_seams(request)


@router.get(
    "/health",
    response_model=SkillTriadHealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Health check endpoint for skill triad subsystem",
)
async def skill_triad_health() -> SkillTriadHealthResponse:
    """Returns operational health status of skill triad subsystem."""
    return SkillTriadHealthResponse()
