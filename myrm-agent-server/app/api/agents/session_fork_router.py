"""FastAPI router for Pi Harness v2 Deterministic Subagent Session Fork Primitive (Item 51).

[INPUT]
- app.schemas.session_fork::{
    ForkChildSessionRequest,
    DeriveChildIdRequest,
  }
- app.services.agent.session_fork_service::{
    SessionForkService,
    get_session_fork_service,
  }

[OUTPUT]
- REST endpoints under /agents/session-fork for deterministic child derivation,
  safe replay reattachment, node inspection, and child session directory.

[POS]
- HTTP API layer for deterministic session fork subsystem.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Path, status
from myrm_agent_harness.agent.sub_agents.session_fork import (
    ForkConflictError,
)

from app.schemas.responses import StandardSuccessResponse, create_success_response
from app.schemas.session_fork import (
    DeriveChildIdRequest,
    ForkChildSessionRequest,
)
from app.services.agent.session_fork_service import (
    SessionForkService,
    get_session_fork_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Pi Harness v2 Deterministic Subagent Session Fork"])


def get_service() -> SessionForkService:
    """Dependency injector for SessionForkService."""
    return get_session_fork_service()


@router.post(
    "/agents/session-fork/derive-id",
    response_model=StandardSuccessResponse,
    status_code=status.HTTP_200_OK,
    summary="Deterministically compute child session ID without mutating state",
)
def derive_child_id_endpoint(
    payload: DeriveChildIdRequest = ...,
    service: SessionForkService = Depends(get_service),
) -> StandardSuccessResponse:
    res = service.derive_child_session_id(
        parent_session_id=payload.parent_session_id,
        tool_call_id=payload.tool_call_id,
    )
    return create_success_response(data=res.model_dump())


@router.post(
    "/agents/session-fork/fork",
    response_model=StandardSuccessResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Fork child session or safely reattach if identical invocation replays",
)
def fork_child_session_endpoint(
    payload: ForkChildSessionRequest = ...,
    service: SessionForkService = Depends(get_service),
) -> StandardSuccessResponse:
    try:
        res = service.fork_child_session(payload)
        return create_success_response(data=res.model_dump())
    except ForkConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc


@router.get(
    "/agents/session-fork/children/{child_session_id}",
    response_model=StandardSuccessResponse,
    status_code=status.HTTP_200_OK,
    summary="Get linkage and reattach tracking for a deterministic child session",
)
def get_child_session_endpoint(
    child_session_id: str = Path(..., description="Child session ID"),
    service: SessionForkService = Depends(get_service),
) -> StandardSuccessResponse:
    link = service.get_child_session(child_session_id)
    if link is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Child session '{child_session_id}' not found",
        )
    return create_success_response(data=link.model_dump())


@router.get(
    "/agents/session-fork/children/{child_session_id}/nodes",
    response_model=StandardSuccessResponse,
    status_code=status.HTTP_200_OK,
    summary="Get copied entry nodes inside a forked child session",
)
def get_child_nodes_endpoint(
    child_session_id: str = Path(..., description="Child session ID"),
    service: SessionForkService = Depends(get_service),
) -> StandardSuccessResponse:
    link = service.get_child_session(child_session_id)
    if link is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Child session '{child_session_id}' not found",
        )
    nodes = service.get_child_nodes(child_session_id)
    return create_success_response(data=[n.model_dump() for n in nodes])


@router.get(
    "/agents/session-fork/parents/{parent_session_id}/children",
    response_model=StandardSuccessResponse,
    status_code=status.HTTP_200_OK,
    summary="List all child sessions forked under a parent session",
)
def list_children_for_parent_endpoint(
    parent_session_id: str = Path(..., description="Parent session ID"),
    service: SessionForkService = Depends(get_service),
) -> StandardSuccessResponse:
    res = service.list_children_for_parent(parent_session_id)
    return create_success_response(data=res.model_dump())


@router.post(
    "/agents/session-fork/reset",
    response_model=StandardSuccessResponse,
    status_code=status.HTTP_200_OK,
    summary="Reset session fork repository cache",
)
def reset_session_fork_endpoint(
    service: SessionForkService = Depends(get_service),
) -> StandardSuccessResponse:
    service.reset()
    return create_success_response(data={"message": "Session fork manager reset successfully."})
