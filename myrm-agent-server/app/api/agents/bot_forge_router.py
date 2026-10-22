"""FastAPI endpoints for Chat-Driven Agent & Team Factory with Builder Safety Envelope."""

from __future__ import annotations

from typing import Dict

from fastapi import APIRouter, Depends, HTTPException, status
from myrm_agent_harness.agent.sub_agents.bot_forge import (
    BuilderSafetyViolationError,
)

from app.schemas.bot_forge import (
    BotForgeCatalogResponseDTO,
    BotProfileSpecDTO,
    CloneAgentRequestDTO,
    OverlapCheckRequestDTO,
    OverlapCheckResponseDTO,
    PipelineExecutionStateDTO,
    SingleAgentCreationRequestDTO,
    TeamCreationRequestDTO,
)
from app.services.agent.bot_forge_service import (
    BotForgeService,
    get_bot_forge_service,
)

router = APIRouter(prefix="/agents/bot-forge", tags=["bot-forge"])


@router.post(
    "/sessions/{session_id}/check-overlap",
    response_model=OverlapCheckResponseDTO,
    summary="Check proposed agent name and duty overlap against active catalog",
)
def check_overlap(
    session_id: str,
    req: OverlapCheckRequestDTO,
    service: BotForgeService = Depends(get_bot_forge_service),
) -> OverlapCheckResponseDTO:
    """Analyze name uniqueness and lexical duty similarity before agent creation."""
    return service.check_overlap(session_id=session_id, req=req)


@router.post(
    "/sessions/{session_id}/create-agent",
    response_model=PipelineExecutionStateDTO,
    status_code=status.HTTP_201_CREATED,
    summary="Create an individual agent through verified pipeline",
)
def create_agent(
    session_id: str,
    req: SingleAgentCreationRequestDTO,
    service: BotForgeService = Depends(get_bot_forge_service),
) -> PipelineExecutionStateDTO:
    """Instantiate a single agent with dry-run readiness check and rollback on failure."""
    try:
        return service.create_agent(session_id=session_id, req=req)
    except BuilderSafetyViolationError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Builder safety envelope violation: {err}",
        ) from err


@router.post(
    "/sessions/{session_id}/create-team",
    response_model=PipelineExecutionStateDTO,
    status_code=status.HTTP_201_CREATED,
    summary="Create a multi-agent squad with atomic rollback",
)
def create_team(
    session_id: str,
    req: TeamCreationRequestDTO,
    service: BotForgeService = Depends(get_bot_forge_service),
) -> PipelineExecutionStateDTO:
    """Instantiate a team squad; if any member fails, roll back all created members atomically."""
    try:
        return service.create_team(session_id=session_id, req=req)
    except BuilderSafetyViolationError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Builder safety envelope violation: {err}",
        ) from err


@router.post(
    "/sessions/{session_id}/clone-agent",
    response_model=PipelineExecutionStateDTO,
    status_code=status.HTTP_201_CREATED,
    summary="Clone an existing agent with prompt name sanitization",
)
def clone_agent(
    session_id: str,
    req: CloneAgentRequestDTO,
    service: BotForgeService = Depends(get_bot_forge_service),
) -> PipelineExecutionStateDTO:
    """Clone an agent profile while sanitizing references to the old agent name."""
    try:
        return service.clone_agent(session_id=session_id, req=req)
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(err),
        ) from err
    except BuilderSafetyViolationError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Builder safety envelope violation: {err}",
        ) from err


@router.get(
    "/sessions/{session_id}/agents",
    response_model=BotForgeCatalogResponseDTO,
    summary="List all provisioned agents in session",
)
def list_agents(
    session_id: str,
    service: BotForgeService = Depends(get_bot_forge_service),
) -> BotForgeCatalogResponseDTO:
    """Retrieve catalog of all active agents in session."""
    return service.list_agents(session_id=session_id)


@router.get(
    "/sessions/{session_id}/agents/{name}",
    response_model=BotProfileSpecDTO,
    summary="Get single agent profile specification by name",
)
def get_agent(
    session_id: str,
    name: str,
    service: BotForgeService = Depends(get_bot_forge_service),
) -> BotProfileSpecDTO:
    """Retrieve profile specification for a specific agent."""
    agent = service.get_agent(session_id=session_id, name=name)
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent '{name}' not found in session '{session_id}'.",
        )
    return agent


@router.delete(
    "/sessions/{session_id}/agents/{name}",
    response_model=Dict[str, str],
    summary="Delete an agent from session store",
)
def delete_agent(
    session_id: str,
    name: str,
    service: BotForgeService = Depends(get_bot_forge_service),
) -> Dict[str, str]:
    """Delete an agent from session store."""
    deleted = service.delete_agent(session_id=session_id, name=name)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent '{name}' not found in session '{session_id}'.",
        )
    return {"status": "deleted", "name": name}
