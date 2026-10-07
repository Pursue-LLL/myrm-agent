# [POS]: app/api/memory/thinking_sanitizer_router.py
# [INPUT]: app.schemas.thinking_sanitizer, app.services.memory.thinking_sanitizer_service
# [OUTPUT]: router

"""FastAPI router for Thinking Block Sanitizer & Prompt Contamination Shield (Item 115)."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.schemas.thinking_sanitizer import (
    CheckUsableSummaryRequest,
    SanitizationResultDTO,
    SanitizeTextRequest,
    UsableSummaryCheckResponse,
)
from app.services.memory.thinking_sanitizer_service import (
    ThinkingSanitizerService,
    get_thinking_sanitizer_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/thinking-sanitizer",
    tags=["Memory - Thinking Block Sanitizer"],
)


@router.post(
    "/sanitize",
    response_model=SanitizationResultDTO,
    status_code=status.HTTP_200_OK,
    summary="Sanitize reasoning channels and planning drafts from text",
)
async def sanitize_text(
    payload: SanitizeTextRequest,
    service: Annotated[ThinkingSanitizerService, Depends(get_thinking_sanitizer_service)],
) -> SanitizationResultDTO:
    """Scrub paired thinking blocks, orphan close tags, and planning lead-ins."""
    return service.sanitize(payload.text, payload.config)


@router.post(
    "/usable-check",
    response_model=UsableSummaryCheckResponse,
    status_code=status.HTTP_200_OK,
    summary="Evaluate summary egress safety for prompt context injection",
)
async def check_usable_summary(
    payload: CheckUsableSummaryRequest,
    service: Annotated[ThinkingSanitizerService, Depends(get_thinking_sanitizer_service)],
) -> UsableSummaryCheckResponse:
    """Evaluate candidate summary against egress usability guards."""
    return service.check_usable_summary(payload.text, payload.config)
