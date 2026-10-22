"""FastAPI router for Goal-Driven Autonomous Orchestration Loop (Item 38).

[INPUT]
- app.schemas.autonomous_loop::{
    StartAutonomousLoopRequest,
    AdvanceStepRequest,
    SetModeRequest,
    CompleteLoopRequest,
  }
- app.services.agent.autonomous_loop_service::{
    AutonomousLoopService,
    get_autonomous_loop_service,
  }

[OUTPUT]
- Router mounted under /chats/{chat_id}/autonomous-loop.

[POS]
- HTTP endpoints for starting autonomous loops, advancing steps, switching modes, and reading loop state.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Path, status

from app.schemas.autonomous_loop import (
    AdvanceStepRequest,
    CompleteLoopRequest,
    SetModeRequest,
    StartAutonomousLoopRequest,
)
from app.schemas.responses import StandardSuccessResponse, create_success_response
from app.services.agent.autonomous_loop_service import (
    AutonomousLoopService,
    get_autonomous_loop_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chats/{chat_id}/autonomous-loop", tags=["Autonomous Orchestration Loop"])


@router.post(
    "/start",
    response_model=StandardSuccessResponse,
    summary="Initialize and start an autonomous orchestration loop for a goal",
)
def start_autonomous_loop_endpoint(
    chat_id: str = Path(..., min_length=1, description="Unique chat session identifier"),
    req: StartAutonomousLoopRequest = ...,
    service: AutonomousLoopService = Depends(get_autonomous_loop_service),
) -> StandardSuccessResponse:
    """Initialize autonomous or supervised orchestration loop with step watchdog constraints."""
    if req.session_id != chat_id:
        req = StartAutonomousLoopRequest(
            session_id=chat_id,
            goal_id=req.goal_id,
            mode=req.mode,
            config=req.config,
        )
    state = service.start_loop(req=req)
    return create_success_response(data=state)


@router.get(
    "/state",
    response_model=StandardSuccessResponse,
    summary="Retrieve real-time state and progression history of the loop",
)
def get_autonomous_loop_state_endpoint(
    chat_id: str = Path(..., min_length=1, description="Unique chat session identifier"),
    service: AutonomousLoopService = Depends(get_autonomous_loop_service),
) -> StandardSuccessResponse:
    """Fetch active step count, pacing mode, watchdog budget, and step audit records."""
    state = service.get_state(session_id=chat_id)
    if state is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No autonomous loop found for chat '{chat_id}'",
        )
    return create_success_response(data=state)


@router.post(
    "/advance",
    response_model=StandardSuccessResponse,
    summary="Advance the autonomous loop by one step",
)
def advance_autonomous_loop_step_endpoint(
    chat_id: str = Path(..., min_length=1, description="Unique chat session identifier"),
    req: AdvanceStepRequest = ...,
    service: AutonomousLoopService = Depends(get_autonomous_loop_service),
) -> StandardSuccessResponse:
    """Execute next autonomous step with safety watchdog gates (approval, error, step budget)."""
    try:
        updated_state = service.advance_step(session_id=chat_id, req=req)
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    return create_success_response(data=updated_state)


@router.post(
    "/mode",
    response_model=StandardSuccessResponse,
    summary="Switch orchestration mode (e.g. Autonomous, Supervised, Paused)",
)
def set_orchestration_mode_endpoint(
    chat_id: str = Path(..., min_length=1, description="Unique chat session identifier"),
    req: SetModeRequest = ...,
    service: AutonomousLoopService = Depends(get_autonomous_loop_service),
) -> StandardSuccessResponse:
    """Toggle between autonomous cruising and supervised manual pacing."""
    try:
        updated_state = service.set_mode(session_id=chat_id, req=req)
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    return create_success_response(data=updated_state)


@router.post(
    "/complete",
    response_model=StandardSuccessResponse,
    summary="Mark the autonomous loop as successfully completed",
)
def complete_autonomous_loop_endpoint(
    chat_id: str = Path(..., min_length=1, description="Unique chat session identifier"),
    req: CompleteLoopRequest = ...,
    service: AutonomousLoopService = Depends(get_autonomous_loop_service),
) -> StandardSuccessResponse:
    """Finalize autonomous execution for current goal."""
    try:
        completed_state = service.complete_loop(session_id=chat_id, req=req)
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    return create_success_response(data=completed_state)


@router.delete(
    "",
    response_model=StandardSuccessResponse,
    summary="Reset and clear autonomous loop state for session",
)
def reset_autonomous_loop_endpoint(
    chat_id: str = Path(..., min_length=1, description="Unique chat session identifier"),
    service: AutonomousLoopService = Depends(get_autonomous_loop_service),
) -> StandardSuccessResponse:
    """Clear loop tracker and memory state for session."""
    service.reset_loop(session_id=chat_id)
    return create_success_response(data={"reset": True, "chat_id": chat_id})
