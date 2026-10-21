"""FastAPI REST router for Durable Agent Teams (Item 28).

[INPUT]
- app.schemas.agent_teams::(SpawnTeammateRequest, FailTeammateRequest,
                            TeamMemberResponse, CreateTeamTaskRequest,
                            UpdateTeamTaskRequest, ClaimTeamTaskRequest,
                            CompleteTeamTaskRequest, TeamTaskResponse,
                            SendTeamMessageRequest, DrainInboxResponse,
                            TeamMessageResponse, TeamProjectionResponse)
- app.services.agent.agent_teams_service::(get_agent_teams_service, AgentTeamsService)
- myrm_agent_harness.agent.sub_agents.teams::(CASConflictError, TaskBlockedError, TaskDependencyCycleError)

[OUTPUT]
- router: APIRouter for agent teams endpoints

[POS]
REST API facade for Durable Agent Teams, CAS Task Board DAG, and Peer Mailbox.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from myrm_agent_harness.agent.sub_agents.teams import (
    CASConflictError,
    TaskBlockedError,
    TaskDependencyCycleError,
)

from app.schemas.agent_teams import (
    ClaimTeamTaskRequest,
    CompleteTeamTaskRequest,
    CreateTeamTaskRequest,
    DrainInboxResponse,
    FailTeammateRequest,
    SendTeamMessageRequest,
    SpawnTeammateRequest,
    TeamMemberResponse,
    TeamMessageResponse,
    TeamProjectionResponse,
    TeamTaskResponse,
    UpdateTeamTaskRequest,
)
from app.services.agent.agent_teams_service import (
    AgentTeamsService,
    get_agent_teams_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/teams", tags=["Agent Teams"])


# -----------------------------------------------------------------------------
# Projection & Life-cycle
# -----------------------------------------------------------------------------

@router.get("/{team_id}/projection", response_model=TeamProjectionResponse)
def get_team_projection(
    team_id: str,
    service: Annotated[AgentTeamsService, Depends(get_agent_teams_service)],
) -> TeamProjectionResponse:
    """Retrieve full durable team projection (roster, tasks, status)."""
    return service.get_projection(team_id=team_id)


@router.get("/{team_id}/wait")
async def wait_team_change(
    team_id: str,
    service: Annotated[AgentTeamsService, Depends(get_agent_teams_service)],
    timeout_sec: float = Query(default=10.0, ge=0.5, le=60.0),
) -> dict[str, bool]:
    """Wait for edge-triggered domain state change within timeout."""
    changed = await service.wait_for_change(team_id=team_id, timeout_sec=timeout_sec)
    return {"changed": changed}


# -----------------------------------------------------------------------------
# Roster Endpoints
# -----------------------------------------------------------------------------

@router.get("/{team_id}/members", response_model=list[TeamMemberResponse])
def list_team_members(
    team_id: str,
    service: Annotated[AgentTeamsService, Depends(get_agent_teams_service)],
) -> list[TeamMemberResponse]:
    """List all members in the team roster."""
    return service.list_members(team_id=team_id)


@router.post("/{team_id}/members", response_model=TeamMemberResponse, status_code=status.HTTP_201_CREATED)
def spawn_teammate(
    team_id: str,
    request: SpawnTeammateRequest,
    service: Annotated[AgentTeamsService, Depends(get_agent_teams_service)],
) -> TeamMemberResponse:
    """Spawn and register a new kebab-case named teammate."""
    try:
        return service.spawn_teammate(team_id=team_id, request=request)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/{team_id}/members/{name}/fail", response_model=TeamMemberResponse)
def fail_teammate(
    team_id: str,
    name: str,
    request: FailTeammateRequest,
    service: Annotated[AgentTeamsService, Depends(get_agent_teams_service)],
) -> TeamMemberResponse:
    """Mark a teammate as failed with diagnosis."""
    try:
        return service.fail_teammate(team_id=team_id, name=name, error=request.error)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


# -----------------------------------------------------------------------------
# Task Board Endpoints
# -----------------------------------------------------------------------------

@router.get("/{team_id}/tasks", response_model=list[TeamTaskResponse])
def list_team_tasks(
    team_id: str,
    service: Annotated[AgentTeamsService, Depends(get_agent_teams_service)],
    include_deleted: bool = Query(default=False),
) -> list[TeamTaskResponse]:
    """List tasks on the shared board."""
    return service.list_tasks(team_id=team_id, include_deleted=include_deleted)


@router.post("/{team_id}/tasks", response_model=TeamTaskResponse, status_code=status.HTTP_201_CREATED)
def create_team_task(
    team_id: str,
    request: CreateTeamTaskRequest,
    service: Annotated[AgentTeamsService, Depends(get_agent_teams_service)],
) -> TeamTaskResponse:
    """Create an unowned pending task (revision 1)."""
    try:
        return service.create_task(team_id=team_id, request=request)
    except TaskDependencyCycleError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/{team_id}/tasks/{task_id}", response_model=TeamTaskResponse)
def get_team_task(
    team_id: str,
    task_id: str,
    service: Annotated[AgentTeamsService, Depends(get_agent_teams_service)],
) -> TeamTaskResponse:
    """Get single task view."""
    try:
        return service.get_task(team_id=team_id, task_id=task_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/{team_id}/tasks/{task_id}/claim", response_model=TeamTaskResponse)
def claim_team_task(
    team_id: str,
    task_id: str,
    request: ClaimTeamTaskRequest,
    service: Annotated[AgentTeamsService, Depends(get_agent_teams_service)],
) -> TeamTaskResponse:
    """Claim an unowned, ready task using CAS."""
    try:
        return service.claim_task(team_id=team_id, task_id=task_id, request=request)
    except CASConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except TaskBlockedError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/{team_id}/tasks/{task_id}/complete", response_model=TeamTaskResponse)
def complete_team_task(
    team_id: str,
    task_id: str,
    request: CompleteTeamTaskRequest,
    service: Annotated[AgentTeamsService, Depends(get_agent_teams_service)],
) -> TeamTaskResponse:
    """Mark a task as completed using CAS."""
    try:
        return service.complete_task(team_id=team_id, task_id=task_id, request=request)
    except CASConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/{team_id}/tasks/{task_id}/update", response_model=TeamTaskResponse)
def update_team_task(
    team_id: str,
    task_id: str,
    request: UpdateTeamTaskRequest,
    service: Annotated[AgentTeamsService, Depends(get_agent_teams_service)],
) -> TeamTaskResponse:
    """Update a task guarded by CAS revision."""
    try:
        return service.update_task(team_id=team_id, task_id=task_id, request=request)
    except CASConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except TaskDependencyCycleError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


# -----------------------------------------------------------------------------
# Peer Mailbox Endpoints
# -----------------------------------------------------------------------------

@router.post("/{team_id}/messages", response_model=TeamMessageResponse, status_code=status.HTTP_201_CREATED)
def send_team_peer_message(
    team_id: str,
    request: SendTeamMessageRequest,
    service: Annotated[AgentTeamsService, Depends(get_agent_teams_service)],
) -> TeamMessageResponse:
    """Send a peer-to-peer message to another teammate."""
    try:
        return service.send_message(team_id=team_id, request=request)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(exc)) from exc


@router.post("/{team_id}/messages/{member_name}/drain", response_model=DrainInboxResponse)
def drain_team_inbox(
    team_id: str,
    member_name: str,
    service: Annotated[AgentTeamsService, Depends(get_agent_teams_service)],
) -> DrainInboxResponse:
    """Drain and deliver pending messages for a teammate."""
    try:
        return service.drain_inbox(team_id=team_id, member_name=member_name)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/{team_id}/messages/history")
def list_team_message_history(
    team_id: str,
    service: Annotated[AgentTeamsService, Depends(get_agent_teams_service)],
    limit: int = Query(default=100, ge=1, le=500),
) -> list[dict[str, object]]:
    """Get audit trail of historical peer messages."""
    return service.list_message_history(team_id=team_id, limit=limit)
