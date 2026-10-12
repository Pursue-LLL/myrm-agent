"""FastAPI router for knowledge graph pre-extraction content screening and anti-poisoning.

[INPUT]
- fastapi
- app.schemas.kg_screening::*
- app.services.memory.kg_screening_service::*

[OUTPUT]
- router: APIRouter instance exposing KG screening endpoints

[POS]
API boundary for screening raw text candidates and inspecting security audit logs before graph extraction.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status

from app.schemas.kg_screening import (
    ScreenContentRequestDTO,
    ScreenContentResponseDTO,
    ScreeningAuditListResponseDTO,
)
from app.services.memory.kg_screening_service import (
    KGScreeningService,
    get_kg_screening_service,
)

router = APIRouter(prefix="/kg", tags=["memory-kg-screening"])


@router.post(
    "/screen-content",
    response_model=ScreenContentResponseDTO,
    status_code=status.HTTP_200_OK,
    summary="Screen and sanitize text against prompt injection before knowledge graph extraction",
)
def screen_extraction_content(
    request: ScreenContentRequestDTO,
    service: KGScreeningService = Depends(get_kg_screening_service),
) -> ScreenContentResponseDTO:
    """Evaluate text for hidden HTML comments, zero-width steganography, and system prompt overrides."""
    return service.screen_content(request)


@router.get(
    "/screening-audit-log",
    response_model=ScreeningAuditListResponseDTO,
    status_code=status.HTTP_200_OK,
    summary="Fetch security screening audit logs and blocked injection records",
)
def get_screening_audit_log(
    limit: int = Query(default=50, ge=1, le=500, description="Max audit entries to retrieve"),
    service: KGScreeningService = Depends(get_kg_screening_service),
) -> ScreeningAuditListResponseDTO:
    """Retrieve audit history showing screening verdicts, detected threats, and sanitization actions."""
    return service.get_audit_records(limit=limit)
