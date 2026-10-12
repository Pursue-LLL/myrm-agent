"""API router for HITL Denial Events and Synthetic Tool Result Generation.

[INPUT]
- ProcessDenialsRequest.

[OUTPUT]
- ProcessDenialsResponse.

[POS]
- Security router mounted under /security/hitl-denial.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from app.schemas.hitl_denial import (
    ProcessDenialsRequest,
    ProcessDenialsResponse,
)
from app.services.security.hitl_denial_service import HitlDenialService

router = APIRouter(prefix="/hitl-denial", tags=["hitl-denial"])

_default_service = HitlDenialService()


def get_hitl_denial_service() -> HitlDenialService:
    """Dependency provider for HitlDenialService."""
    return _default_service


@router.post(
    "/process",
    response_model=ProcessDenialsResponse,
    status_code=status.HTTP_200_OK,
    summary="Process HITL user denials and generate synthetic ToolResult blocks",
)
async def process_hitl_denials(
    request: ProcessDenialsRequest,
    service: HitlDenialService = Depends(get_hitl_denial_service),
) -> ProcessDenialsResponse:
    """Transform manual tool denials into context-preserving tool error messages."""
    return service.process_denials(request)
