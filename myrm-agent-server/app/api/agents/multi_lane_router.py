"""FastAPI router for Pi Harness v2 Multi-Lane Parallel Execution Model (Item 50).

[INPUT]
- app.schemas.multi_lane::{
    CreateLaneRequest,
    AppendNodeRequest,
    DispatchOperationRequest,
    CompleteOperationRequest,
    CancelOperationRequest,
  }
- app.services.agent.multi_lane_service::{
    MultiLaneService,
    get_multi_lane_service,
  }

[OUTPUT]
- REST endpoints under /chats/{chat_id}/multi-lane for parallel lane management,
  operation dispatching, op log inspection, and shared tree append.

[POS]
- HTTP API layer for session-scoped multi-lane execution.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from myrm_agent_harness.agent.sub_agents.multi_lane import (
    LaneConcurrencyConflictError,
    LaneNotFoundError,
    NodeNotFoundError,
    OperationNotFoundError,
)

from app.schemas.multi_lane import (
    AppendNodeRequest,
    CancelOperationRequest,
    CompleteOperationRequest,
    CreateLaneRequest,
    DispatchOperationRequest,
)
from app.schemas.responses import StandardSuccessResponse, create_success_response
from app.services.agent.multi_lane_service import (
    MultiLaneService,
    get_multi_lane_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Pi Harness v2 Multi-Lane Parallel Execution"])


def get_service() -> MultiLaneService:
    """Dependency injector for MultiLaneService."""
    return get_multi_lane_service()


@router.post(
    "/chats/{chat_id}/multi-lane/lanes",
    response_model=StandardSuccessResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create or register a new lane within session",
)
async def create_lane_endpoint(
    chat_id: str = Path(..., description="Unique chat session ID"),
    payload: CreateLaneRequest = ...,
    service: MultiLaneService = Depends(get_service),
) -> StandardSuccessResponse:
    try:
        lane = await service.create_lane(
            session_id=chat_id,
            lane_id=payload.lane_id,
            display_name=payload.display_name,
            fork_from_node_id=payload.fork_from_node_id,
        )
        return create_success_response(data=lane.model_dump())
    except NodeNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get(
    "/chats/{chat_id}/multi-lane/snapshot",
    response_model=StandardSuccessResponse,
    status_code=status.HTTP_200_OK,
    summary="Get global snapshot of all lanes and tree topology",
)
async def get_snapshot_endpoint(
    chat_id: str = Path(..., description="Unique chat session ID"),
    limit: int = Query(default=50, ge=1, le=200, description="Recent op logs limit"),
    service: MultiLaneService = Depends(get_service),
) -> StandardSuccessResponse:
    snapshot = await service.get_snapshot(session_id=chat_id, recent_ops_limit=limit)
    return create_success_response(data=snapshot.model_dump())


@router.post(
    "/chats/{chat_id}/multi-lane/lanes/{lane_id}/nodes",
    response_model=StandardSuccessResponse,
    status_code=status.HTTP_200_OK,
    summary="Append a node to shared tree on lane leaf",
)
async def append_node_endpoint(
    chat_id: str = Path(..., description="Unique chat session ID"),
    lane_id: str = Path(..., description="Target lane identifier"),
    payload: AppendNodeRequest = ...,
    service: MultiLaneService = Depends(get_service),
) -> StandardSuccessResponse:
    try:
        node = await service.append_node(
            session_id=chat_id,
            lane_id=lane_id,
            content=payload.content,
            node_type=payload.node_type,
            metadata=payload.metadata,
        )
        return create_success_response(data=node.model_dump())
    except LaneNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post(
    "/chats/{chat_id}/multi-lane/lanes/{lane_id}/dispatch",
    response_model=StandardSuccessResponse,
    status_code=status.HTTP_200_OK,
    summary="Dispatch operation on lane enforcing max 1 open operation constraint",
)
async def dispatch_operation_endpoint(
    chat_id: str = Path(..., description="Unique chat session ID"),
    lane_id: str = Path(..., description="Target lane identifier"),
    payload: DispatchOperationRequest = ...,
    service: MultiLaneService = Depends(get_service),
) -> StandardSuccessResponse:
    try:
        op = await service.dispatch_operation(
            session_id=chat_id,
            lane_id=lane_id,
            name=payload.name,
            payload=payload.payload,
        )
        return create_success_response(data=op.model_dump())
    except LaneNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except LaneConcurrencyConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.post(
    "/chats/{chat_id}/multi-lane/lanes/{lane_id}/complete",
    response_model=StandardSuccessResponse,
    status_code=status.HTTP_200_OK,
    summary="Complete operation on lane and optionally append result to shared tree",
)
async def complete_operation_endpoint(
    chat_id: str = Path(..., description="Unique chat session ID"),
    lane_id: str = Path(..., description="Target lane identifier"),
    payload: CompleteOperationRequest = ...,
    service: MultiLaneService = Depends(get_service),
) -> StandardSuccessResponse:
    try:
        op = await service.complete_operation(
            session_id=chat_id,
            lane_id=lane_id,
            op_id=payload.op_id,
            result_content=payload.result_content,
            error=payload.error,
        )
        return create_success_response(data=op.model_dump())
    except LaneNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except OperationNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post(
    "/chats/{chat_id}/multi-lane/lanes/{lane_id}/cancel",
    response_model=StandardSuccessResponse,
    status_code=status.HTTP_200_OK,
    summary="Cancel in-flight operation on lane",
)
async def cancel_operation_endpoint(
    chat_id: str = Path(..., description="Unique chat session ID"),
    lane_id: str = Path(..., description="Target lane identifier"),
    payload: CancelOperationRequest = ...,
    service: MultiLaneService = Depends(get_service),
) -> StandardSuccessResponse:
    try:
        op = await service.cancel_operation(
            session_id=chat_id,
            lane_id=lane_id,
            op_id=payload.op_id,
            reason=payload.reason,
        )
        return create_success_response(data=op.model_dump())
    except LaneNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except OperationNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get(
    "/chats/{chat_id}/multi-lane/lanes/{lane_id}/oplog",
    response_model=StandardSuccessResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve operation log entries for a lane",
)
async def get_oplog_endpoint(
    chat_id: str = Path(..., description="Unique chat session ID"),
    lane_id: str = Path(..., description="Target lane identifier"),
    service: MultiLaneService = Depends(get_service),
) -> StandardSuccessResponse:
    try:
        ops = await service.get_op_log(session_id=chat_id, lane_id=lane_id)
        return create_success_response(data=[op.model_dump() for op in ops])
    except LaneNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post(
    "/chats/{chat_id}/multi-lane/reset",
    response_model=StandardSuccessResponse,
    status_code=status.HTTP_200_OK,
    summary="Reset session coordinator state",
)
def reset_session_endpoint(
    chat_id: str = Path(..., description="Unique chat session ID"),
    service: MultiLaneService = Depends(get_service),
) -> StandardSuccessResponse:
    service.reset_session(session_id=chat_id)
    return create_success_response(data={"message": f"Session '{chat_id}' multi-lane state reset successfully."})
