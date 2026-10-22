"""FastAPI router for Conversational Multi-Specialist Summoning & Context Aggregation (Item 54).

[INPUT]
- app.schemas.specialist_summoning::{
    SummonSpecialistRequest,
    DetectIntentRequest,
  }
- app.services.agent.specialist_summoning_service::{
    SpecialistSummoningService,
  }

[OUTPUT]
- REST endpoints under /agents/specialists and /chats/{chat_id}/specialists
  for specialist catalog discovery, intent detection, isolated summoning,
  and structured aggregation card retrieval.

[POS]
- HTTP API layer for conversational multi-specialist summoning & structured return pack.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Path, status

from app.schemas.responses import StandardSuccessResponse, create_success_response
from app.schemas.specialist_summoning import (
    DetectIntentRequest,
    SummonSpecialistRequest,
)
from app.services.agent.specialist_summoning_service import SpecialistSummoningService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Conversational Multi-Specialist Summoning"])


def get_service() -> SpecialistSummoningService:
    """Dependency injector for SpecialistSummoningService."""
    return SpecialistSummoningService.get_instance()


@router.get(
    "/agents/specialists/catalog",
    response_model=StandardSuccessResponse,
    status_code=status.HTTP_200_OK,
    summary="Get catalog of all available conversational specialists",
)
async def get_specialist_catalog(
    service: SpecialistSummoningService = Depends(get_service),
) -> StandardSuccessResponse:
    """Retrieve list of all registered specialist profiles available for dynamic summoning."""
    catalog = service.get_catalog()
    return create_success_response(data=[p.model_dump() for p in catalog])


@router.get(
    "/agents/specialists/{specialist_id}",
    response_model=StandardSuccessResponse,
    status_code=status.HTTP_200_OK,
    summary="Get details of a specific specialist by ID",
)
async def get_specialist_detail(
    specialist_id: str = Path(..., description="Target specialist identifier"),
    service: SpecialistSummoningService = Depends(get_service),
) -> StandardSuccessResponse:
    """Retrieve profile metadata for a specific specialist."""
    profile = service.get_specialist(specialist_id)
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Specialist '{specialist_id}' not found in registered catalog.",
        )
    return create_success_response(data=profile.model_dump())


@router.post(
    "/agents/specialists/detect-intent",
    response_model=StandardSuccessResponse,
    status_code=status.HTTP_200_OK,
    summary="Detect @-mention or implicit intent keywords in user message",
)
async def detect_specialist_intent(
    request: DetectIntentRequest,
    service: SpecialistSummoningService = Depends(get_service),
) -> StandardSuccessResponse:
    """Scan message text to detect whether user invoked an expert via @ or implicit keywords."""
    result = service.detect_intent(request.message)
    return create_success_response(data=result.model_dump())


@router.post(
    "/chats/{chat_id}/specialists/summon",
    response_model=StandardSuccessResponse,
    status_code=status.HTTP_200_OK,
    summary="Summon a specialist to execute a task in an isolated sandbox session",
)
async def summon_specialist_endpoint(
    chat_id: str = Path(..., description="Unique chat session identifier"),
    request: SummonSpecialistRequest = ...,
    service: SpecialistSummoningService = Depends(get_service),
) -> StandardSuccessResponse:
    """Dispatch an isolated specialist task and return structured aggregation deliverable card."""
    logger.info("Summoning specialist '%s' for chat '%s'", request.specialist_id, chat_id)
    execution = service.summon_specialist(chat_id, request)
    return create_success_response(data=execution.model_dump())


@router.get(
    "/chats/{chat_id}/specialists/executions",
    response_model=StandardSuccessResponse,
    status_code=status.HTTP_200_OK,
    summary="Get all specialist executions and aggregation cards for a session",
)
async def get_session_executions_endpoint(
    chat_id: str = Path(..., description="Unique chat session identifier"),
    service: SpecialistSummoningService = Depends(get_service),
) -> StandardSuccessResponse:
    """Retrieve history of specialist executions and structured deliverable cards in this chat."""
    executions = service.get_session_executions(chat_id)
    return create_success_response(data=[e.model_dump() for e in executions])


@router.delete(
    "/chats/{chat_id}/specialists/executions",
    response_model=StandardSuccessResponse,
    status_code=status.HTTP_200_OK,
    summary="Clear specialist execution records for a session",
)
async def clear_session_executions_endpoint(
    chat_id: str = Path(..., description="Unique chat session identifier"),
    service: SpecialistSummoningService = Depends(get_service),
) -> StandardSuccessResponse:
    """Clear recorded executions for a session."""
    service.clear_session_executions(chat_id)
    return create_success_response(data={"cleared": True, "chat_id": chat_id})
