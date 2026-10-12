"""API router for Data Plane Injection Defense, Hardened Fencing, and QuotedAsData.

[INPUT]
- FencePayloadRequest, DetectInjectionRequest
- Query parameters: subject, source, raw_text

[OUTPUT]
- FencePayloadResponse, DetectInjectionResponse, QuotedAsDataBadgeDto

[POS]
Server API layer. Exposes REST endpoints for data fencing and UI trust badges.
"""

from __future__ import annotations

from fastapi import APIRouter, Query

from app.schemas.data_plane_defense import (
    DetectInjectionRequest,
    DetectInjectionResponse,
    FencePayloadRequest,
    FencePayloadResponse,
    QuotedAsDataBadgeDto,
)
from app.services.security.data_plane_defense_service import (
    default_data_plane_defense_service,
)

router = APIRouter(prefix="/data-plane", tags=["data-plane"])


@router.post("/fence", response_model=FencePayloadResponse)
async def fence_external_data(
    request: FencePayloadRequest,
) -> FencePayloadResponse:
    """Sanitize and fence external third-party strings to neutralize prompt injections."""
    return default_data_plane_defense_service.fence_data(request)


@router.post("/detect", response_model=DetectInjectionResponse)
async def detect_prompt_injection(
    request: DetectInjectionRequest,
) -> DetectInjectionResponse:
    """Evaluate text against user-plane jailbreaks or data-plane indirect injection rules."""
    return default_data_plane_defense_service.detect_injection(request)


@router.get("/badge-preview", response_model=QuotedAsDataBadgeDto)
async def get_quoted_as_data_badge(
    raw_text: str = Query(..., description="External raw text"),
    subject: str = Query(default="用户评价", description="Content subject label"),
    source: str = Query(default="第三方数据源", description="Source name"),
) -> QuotedAsDataBadgeDto:
    """Generate QuotedAsData trust badge preview and sanitized content for UI rendering."""
    return default_data_plane_defense_service.generate_quoted_badge(
        raw_text=raw_text,
        subject=subject,
        source=source,
    )
