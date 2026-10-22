"""Agent Session Multiplexer REST API router.

[INPUT]
- fastapi::APIRouter, Depends, HTTPException, Query, status
- app.services.agent.agent_multiplexer_service::(
    AgentMultiplexerService,
    InjectInstructionRequest,
    InjectInstructionResponse,
    MultiplexerInspectDTO,
    MultiplexerSessionSummaryDTO,
    RegisterMultiplexerSessionRequest,
  )

[OUTPUT]
- GET /api/v1/agents/multiplexer/sessions: List multiplexed agent sessions.
- POST /api/v1/agents/multiplexer/sessions: Register or attach a multiplexed session.
- GET /api/v1/agents/multiplexer/sessions/{session_id}/inspect: Inspect logs and artifacts.
- POST /api/v1/agents/multiplexer/sessions/{session_id}/instruct: Inject steering instruction.

[POS]
REST API endpoints enabling GUI and CLI multiplexer consoles to inspect and steer agents.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status

from app.services.agent.agent_multiplexer_service import (
    AgentMultiplexerService,
    InjectInstructionRequest,
    InjectInstructionResponse,
    MultiplexerInspectDTO,
    MultiplexerSessionSummaryDTO,
    RegisterMultiplexerSessionRequest,
)

router = APIRouter(prefix="/agents/multiplexer", tags=["Agent Multiplexer"])
_service = AgentMultiplexerService()


@router.get(
    "/sessions",
    response_model=list[MultiplexerSessionSummaryDTO],
    status_code=status.HTTP_200_OK,
    summary="List active multiplexed agent sessions",
)
async def list_multiplexer_sessions(
    parent_session_id: str | None = Query(default=None, description="Filter by parent root session"),
    state: str | None = Query(default=None, description="Filter by state (running, blocked, etc.)"),
    is_headless: bool | None = Query(default=None, description="Filter by headless worker flag"),
) -> list[MultiplexerSessionSummaryDTO]:
    """Retrieve all tracked multiplexed sessions matching optional criteria."""
    return _service.list_sessions(
        parent_session_id=parent_session_id,
        state=state,
        is_headless=is_headless,
    )


@router.post(
    "/sessions",
    response_model=MultiplexerSessionSummaryDTO,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new multiplexed session",
)
async def register_multiplexer_session(
    request: RegisterMultiplexerSessionRequest,
) -> MultiplexerSessionSummaryDTO:
    """Register or attach a new agent session into multiplexer control."""
    return _service.register_session(request)


@router.get(
    "/sessions/{session_id}/inspect",
    response_model=MultiplexerInspectDTO,
    status_code=status.HTTP_200_OK,
    summary="Inspect status, execution logs, and artifacts of a session",
)
async def inspect_multiplexer_session(
    session_id: str,
    tail_lines: int = Query(default=50, ge=5, le=200, description="Number of recent log lines"),
) -> MultiplexerInspectDTO:
    """Capture a read-only snapshot of a concurrent agent session without interrupting it."""
    snapshot = _service.inspect_session(session_id, tail_lines=tail_lines)
    if not snapshot:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Multiplexed session '{session_id}' not found.",
        )
    return snapshot


@router.post(
    "/sessions/{session_id}/instruct",
    response_model=InjectInstructionResponse,
    status_code=status.HTTP_200_OK,
    summary="Inject interactive instruction or steering guidance into a session",
)
async def instruct_multiplexer_session(
    session_id: str,
    request: InjectInstructionRequest,
) -> InjectInstructionResponse:
    """Inject clarification, guidance, or parameter correction into target session."""
    result = _service.instruct_session(session_id, request)
    if not result.success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=result.message,
        )
    return result
