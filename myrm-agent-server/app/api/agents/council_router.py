"""FastAPI router for Council of Agents Multi-Model Deliberation Protocol (Item 65).

[INPUT]
- app.schemas.council::{
    CreateCouncilSessionRequest, SubmitProposalRequest, SubmitCritiqueRequest,
    SubmitRebuttalRequest, AdvancePhaseRequest,
  }
- app.services.agent.council_service::CouncilDeliberationService

[OUTPUT]
- REST endpoints under /agents/council for multi-model deliberation session lifecycle,
  blind proposal submissions, cross-critiques, rebuttals, and consensus arbitration.

[POS]
- HTTP API layer for Item 65 multi-model council deliberation.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, status

from app.schemas.council import (
    AdvancePhaseRequest,
    CreateCouncilSessionRequest,
    SubmitCritiqueRequest,
    SubmitProposalRequest,
    SubmitRebuttalRequest,
)
from app.schemas.responses import StandardSuccessResponse, create_success_response
from app.services.agent.council_service import CouncilDeliberationService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/agents/council",
    tags=["Council of Agents Deliberation Protocol"],
)


@router.post(
    "/sessions",
    response_model=StandardSuccessResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a multi-model council deliberation session",
)
async def create_session(req: CreateCouncilSessionRequest) -> StandardSuccessResponse:
    """Initialize a council deliberation session for high-stakes decision making."""
    try:
        session = CouncilDeliberationService.create_session(req)
        return create_success_response(data=session.model_dump())
    except Exception as exc:
        logger.exception("Failed to create council session: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.get(
    "/sessions",
    response_model=StandardSuccessResponse,
    status_code=status.HTTP_200_OK,
    summary="List all council deliberation sessions",
)
async def list_sessions() -> StandardSuccessResponse:
    """Retrieve all active deliberation council sessions."""
    try:
        sessions = CouncilDeliberationService.list_sessions()
        return create_success_response(data=[s.model_dump() for s in sessions])
    except Exception as exc:
        logger.exception("Failed to list council sessions: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc


@router.get(
    "/sessions/{session_id}",
    response_model=StandardSuccessResponse,
    status_code=status.HTTP_200_OK,
    summary="Get council session details",
)
async def get_session(session_id: str) -> StandardSuccessResponse:
    """Fetch current deliberation session state, proposals, critiques, and consensus."""
    try:
        session = CouncilDeliberationService.get_session(session_id)
        if session is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Council session '{session_id}' not found",
            )
        return create_success_response(data=session.model_dump())
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to fetch council session: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc


@router.post(
    "/sessions/{session_id}/proposals",
    response_model=StandardSuccessResponse,
    status_code=status.HTTP_200_OK,
    summary="Submit an independent model proposal",
)
async def submit_proposal(
    session_id: str,
    req: SubmitProposalRequest,
) -> StandardSuccessResponse:
    """Submit a blind architectural or strategic proposal into the council."""
    try:
        session = CouncilDeliberationService.submit_proposal(session_id, req)
        return create_success_response(data=session.model_dump())
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.exception("Failed to submit council proposal: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.post(
    "/sessions/{session_id}/critiques",
    response_model=StandardSuccessResponse,
    status_code=status.HTTP_200_OK,
    summary="Post an anonymous cross-model critique",
)
async def submit_critique(
    session_id: str,
    req: SubmitCritiqueRequest,
) -> StandardSuccessResponse:
    """Submit a critique targeting a candidate proposal to expose edge cases."""
    try:
        session = CouncilDeliberationService.submit_critique(session_id, req)
        return create_success_response(data=session.model_dump())
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.exception("Failed to submit council critique: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.post(
    "/sessions/{session_id}/critiques/{critique_id}/rebuttal",
    response_model=StandardSuccessResponse,
    status_code=status.HTTP_200_OK,
    summary="Add a defense rebuttal to a critique",
)
async def submit_rebuttal(
    session_id: str,
    critique_id: str,
    req: SubmitRebuttalRequest,
) -> StandardSuccessResponse:
    """Provide a counter-argument or clarification defending the proposal."""
    try:
        session = CouncilDeliberationService.submit_rebuttal(
            session_id=session_id,
            critique_id=critique_id,
            req=req,
        )
        return create_success_response(data=session.model_dump())
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.exception("Failed to submit council rebuttal: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.post(
    "/sessions/{session_id}/advance",
    response_model=StandardSuccessResponse,
    status_code=status.HTTP_200_OK,
    summary="Advance deliberation phase and trigger consensus synthesis",
)
async def advance_phase(
    session_id: str,
    req: AdvancePhaseRequest,
) -> StandardSuccessResponse:
    """Advance the council session to the next phase, triggering weighted consensus if applicable."""
    try:
        session = CouncilDeliberationService.advance_phase(session_id, req)
        return create_success_response(data=session.model_dump())
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.exception("Failed to advance council phase: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
