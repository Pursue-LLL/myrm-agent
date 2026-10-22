"""FastAPI router for Native Subagent Lifecycle Toolchain (Item 46).

[INPUT]
- app.schemas.subagent_lifecycle::{
    SubagentSpawnRequest,
    SubagentSendInputRequest,
    SubagentKillRequest,
    SubagentWaitRequest,
    SubagentStatusEnum,
  }
- app.services.agent.subagent_lifecycle_service::{
    SubagentLifecycleService,
    get_subagent_lifecycle_service,
  }

[OUTPUT]
- REST endpoints under /chats/{chat_id}/subagents for fine-grained subagent
  lifecycle management (spawn, wait, list, send_input, kill).

[POS]
- HTTP API layer for native subagent operations and control.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from myrm_agent_harness.agent.sub_agents.lifecycle_toolchain import (
    SubagentLifecycleError,
    SubagentNotFoundError,
)

from app.schemas.responses import StandardSuccessResponse, create_success_response
from app.schemas.subagent_lifecycle import (
    SubagentKillRequest,
    SubagentSendInputRequest,
    SubagentSpawnRequest,
    SubagentStatusEnum,
    SubagentWaitRequest,
)
from app.services.agent.subagent_lifecycle_service import (
    SubagentLifecycleService,
    get_subagent_lifecycle_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Native Subagent Lifecycle Toolchain"])


@router.post(
    "/chats/{chat_id}/subagents/spawn",
    response_model=StandardSuccessResponse,
    summary="Spawn an isolated native subagent",
)
def spawn_subagent_endpoint(
    chat_id: str = Path(..., min_length=1, description="Chat session ID"),
    req: SubagentSpawnRequest = ...,
    service: SubagentLifecycleService = Depends(get_subagent_lifecycle_service),
) -> StandardSuccessResponse:
    """Spawn a subagent process tied to the current chat session."""
    try:
        dto = service.spawn_subagent(chat_id=chat_id, request=req)
        return create_success_response(data=dto.model_dump())
    except SubagentLifecycleError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err),
        ) from err


@router.post(
    "/chats/{chat_id}/subagents/wait",
    response_model=StandardSuccessResponse,
    summary="Wait for a batch of subagents to reach terminal state",
)
def wait_subagents_endpoint(
    chat_id: str = Path(..., min_length=1, description="Chat session ID"),
    req: SubagentWaitRequest = ...,
    service: SubagentLifecycleService = Depends(get_subagent_lifecycle_service),
) -> StandardSuccessResponse:
    """Synchronously wait or timeout for multiple subagent tasks."""
    try:
        dto = service.wait_subagents(chat_id=chat_id, request=req)
        return create_success_response(data=dto.model_dump())
    except (SubagentNotFoundError, KeyError) as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(err),
        ) from err
    except SubagentLifecycleError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err),
        ) from err


@router.get(
    "/chats/{chat_id}/subagents",
    response_model=StandardSuccessResponse,
    summary="List subagents under chat session",
)
def list_subagents_endpoint(
    chat_id: str = Path(..., min_length=1, description="Chat session ID"),
    status_filter: SubagentStatusEnum | None = Query(
        default=None, description="Filter by status"
    ),
    limit: int = Query(default=50, ge=1, le=100, description="Max results"),
    service: SubagentLifecycleService = Depends(get_subagent_lifecycle_service),
) -> StandardSuccessResponse:
    """Query subagents belonging to chat session with optional status filter."""
    res = service.list_subagents(
        chat_id=chat_id,
        status_filter=status_filter,
        limit=limit,
    )
    return create_success_response(data=res.model_dump())


@router.get(
    "/chats/{chat_id}/subagents/{subagent_id}",
    response_model=StandardSuccessResponse,
    summary="Get subagent state snapshot",
)
def get_subagent_endpoint(
    chat_id: str = Path(..., min_length=1, description="Chat session ID"),
    subagent_id: str = Path(..., min_length=1, description="Subagent ID"),
    service: SubagentLifecycleService = Depends(get_subagent_lifecycle_service),
) -> StandardSuccessResponse:
    """Retrieve full record and event trace of a subagent."""
    try:
        dto = service.get_subagent(chat_id=chat_id, subagent_id=subagent_id)
        return create_success_response(data=dto.model_dump())
    except (SubagentNotFoundError, KeyError) as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(err),
        ) from err


@router.post(
    "/chats/{chat_id}/subagents/{subagent_id}/input",
    response_model=StandardSuccessResponse,
    summary="Inject supplementary guidance into running subagent",
)
def send_input_endpoint(
    chat_id: str = Path(..., min_length=1, description="Chat session ID"),
    subagent_id: str = Path(..., min_length=1, description="Subagent ID"),
    req: SubagentSendInputRequest = ...,
    service: SubagentLifecycleService = Depends(get_subagent_lifecycle_service),
) -> StandardSuccessResponse:
    """Inject a dynamic steer or correction message into subagent input queue."""
    try:
        msg = service.send_input(
            chat_id=chat_id, subagent_id=subagent_id, request=req
        )
        return create_success_response(data=msg.model_dump())
    except (SubagentNotFoundError, KeyError) as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(err),
        ) from err
    except SubagentLifecycleError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err),
        ) from err


@router.post(
    "/chats/{chat_id}/subagents/{subagent_id}/kill",
    response_model=StandardSuccessResponse,
    summary="Terminate subagent execution",
)
def kill_subagent_endpoint(
    chat_id: str = Path(..., min_length=1, description="Chat session ID"),
    subagent_id: str = Path(..., min_length=1, description="Subagent ID"),
    req: SubagentKillRequest = ...,
    service: SubagentLifecycleService = Depends(get_subagent_lifecycle_service),
) -> StandardSuccessResponse:
    """Terminate subagent execution immediately with audit reason."""
    try:
        dto = service.kill_subagent(
            chat_id=chat_id, subagent_id=subagent_id, request=req
        )
        return create_success_response(data=dto.model_dump())
    except (SubagentNotFoundError, KeyError) as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(err),
        ) from err


@router.post(
    "/chats/{chat_id}/subagents/{subagent_id}/simulate-complete",
    response_model=StandardSuccessResponse,
    summary="Simulate subagent completion",
)
def simulate_complete_endpoint(
    chat_id: str = Path(..., min_length=1, description="Chat session ID"),
    subagent_id: str = Path(..., min_length=1, description="Subagent ID"),
    summary_text: str = Query(default="Task completed successfully"),
    service: SubagentLifecycleService = Depends(get_subagent_lifecycle_service),
) -> StandardSuccessResponse:
    """Simulate subagent successful completion."""
    try:
        dto = service.simulate_complete(
            chat_id=chat_id, subagent_id=subagent_id, result_summary=summary_text
        )
        return create_success_response(data=dto.model_dump())
    except (SubagentNotFoundError, KeyError) as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(err),
        ) from err
