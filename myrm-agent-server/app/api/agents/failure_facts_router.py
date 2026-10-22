"""[INPUT] AnalyzeFailureRequest, chat_id path param, and FailureFactsService.
[OUTPUT] StandardSuccessResponse containing diagnosed StructuredFailureFactDTO or SubagentFailureHistoryResponse.
[POS] FastAPI router for Subagent Bounded Structured Failure Facts & Privacy-Preserving Diagnostic Protocol.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends

from app.schemas.failure_facts import AnalyzeFailureRequest
from app.schemas.responses import StandardSuccessResponse, create_success_response
from app.services.agent.failure_facts_service import (
    FailureFactsService,
    get_failure_facts_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chats/{chat_id}/subagents", tags=["Subagent Failure Facts"])


@router.post(
    "/diagnose-failure",
    response_model=StandardSuccessResponse,
    summary="Diagnose and sanitize a subagent failure fact",
)
def diagnose_failure_endpoint(
    chat_id: str,
    req: AnalyzeFailureRequest,
    service: FailureFactsService = Depends(get_failure_facts_service),
) -> StandardSuccessResponse:
    """Analyze subagent error, map to standard stage/category, scrub sensitive credentials, and bound to <= 4096 bytes."""
    fact_dto = service.diagnose_failure(chat_id=chat_id, req=req)
    return create_success_response(data=fact_dto)


@router.get(
    "/failure-facts",
    response_model=StandardSuccessResponse,
    summary="List recorded failure facts for a chat session",
)
def get_failure_facts_endpoint(
    chat_id: str,
    service: FailureFactsService = Depends(get_failure_facts_service),
) -> StandardSuccessResponse:
    """Fetch history of structured, sanitized failure facts for the given chat session."""
    history = service.get_history(chat_id=chat_id)
    return create_success_response(data=history)


@router.delete(
    "/failure-facts",
    response_model=StandardSuccessResponse,
    summary="Clear failure facts history for a chat session",
)
def cleanup_failure_facts_endpoint(
    chat_id: str,
    service: FailureFactsService = Depends(get_failure_facts_service),
) -> StandardSuccessResponse:
    """Clean up and release failure facts history for a terminated session."""
    cleaned = service.cleanup_chat(chat_id=chat_id)
    return create_success_response(data={"cleaned": cleaned})
