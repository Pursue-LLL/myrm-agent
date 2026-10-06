"""
[POS] app/api/memory/privacy_router.py
[INPUT] fastapi, app/schemas/memory_privacy.py, app/services/memory/memory_privacy_service.py
[OUTPUT] router

FastAPI router exposing memory privacy boundary gate, secret scanning, and redaction endpoints.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from myrm_agent_harness.toolkits.memory.privacy_gate import PrivacyBoundaryViolationError

from app.schemas.memory_privacy import (
    PrivacyCheckRequestDTO,
    PrivacyCheckResponseDTO,
    PrivacyConfigDTO,
    SanitizeContentRequestDTO,
    SanitizeContentResponseDTO,
)
from app.services.memory.memory_privacy_service import (
    MemoryPrivacyService,
    get_memory_privacy_service,
)

router = APIRouter()


@router.post(
    "/privacy/check",
    response_model=PrivacyCheckResponseDTO,
    status_code=status.HTTP_200_OK,
    summary="Evaluate memory text against privacy boundary policies",
)
def check_memory_privacy(
    request: PrivacyCheckRequestDTO,
    service: MemoryPrivacyService = Depends(get_memory_privacy_service),
) -> PrivacyCheckResponseDTO:
    """Check memory content for secrets and exclusion violations without rejecting."""
    return service.check(request)


@router.post(
    "/privacy/sanitize",
    response_model=SanitizeContentResponseDTO,
    status_code=status.HTTP_200_OK,
    summary="Scrub and sanitize secrets from memory candidate text",
)
def sanitize_memory_content(
    request: SanitizeContentRequestDTO,
    service: MemoryPrivacyService = Depends(get_memory_privacy_service),
) -> SanitizeContentResponseDTO:
    """Scrub sensitive credentials from text using semantic placeholders."""
    try:
        return service.sanitize(request)
    except PrivacyBoundaryViolationError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc


@router.post(
    "/privacy/enforce",
    response_model=PrivacyCheckResponseDTO,
    status_code=status.HTTP_200_OK,
    summary="Strictly enforce privacy boundary; raises 403 on critical secret",
)
def enforce_memory_privacy(
    request: PrivacyCheckRequestDTO,
    service: MemoryPrivacyService = Depends(get_memory_privacy_service),
) -> PrivacyCheckResponseDTO:
    """Enforce privacy boundary veto; raises 403 Forbidden if violations are detected."""
    result = service.check(request)
    if not result.passed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=result.violation_reason or "Memory candidate failed privacy boundary evaluation.",
        )
    return result


@router.get(
    "/privacy/config",
    response_model=PrivacyConfigDTO,
    status_code=status.HTTP_200_OK,
    summary="Get active memory privacy gate configuration",
)
def get_privacy_config(
    service: MemoryPrivacyService = Depends(get_memory_privacy_service),
) -> PrivacyConfigDTO:
    """Fetch active privacy gate configuration and patterns."""
    return service.get_config()
