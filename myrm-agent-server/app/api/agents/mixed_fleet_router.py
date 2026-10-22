"""FastAPI router for Mixed Fleet Local Brain and Remote Executor (Item 47).

[INPUT]
- app.schemas.mixed_fleet::{
    DispatchHandoffRequestSchema,
    UpdateFleetHeartbeatRequestSchema,
    CompleteRemoteExecutionRequestSchema,
    FailRemoteExecutionRequestSchema,
  }
- app.services.agent.mixed_fleet_service::{
    MixedFleetService,
    get_mixed_fleet_service,
  }

[OUTPUT]
- REST endpoints under /chats/{chat_id}/mixed-fleet and /agents/mixed-fleet
  for mixed fleet status querying, handoff dispatching, artifact syncing, and heartbeat telemetry.

[POS]
- HTTP API layer for Mixed Fleet Profile presets.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Path, status
from myrm_agent_harness.agent.sub_agents.mixed_fleet import (
    MixedFleetError,
    MixedFleetHandoffNotFoundError,
    MixedFleetOfflineError,
)

from app.schemas.mixed_fleet import (
    CompleteRemoteExecutionRequestSchema,
    DispatchHandoffRequestSchema,
    FailRemoteExecutionRequestSchema,
    UpdateFleetHeartbeatRequestSchema,
)
from app.schemas.responses import StandardSuccessResponse, create_success_response
from app.services.agent.mixed_fleet_service import (
    MixedFleetService,
    get_mixed_fleet_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Mixed Fleet Orchestration"])


@router.get(
    "/agents/mixed-fleet/preset",
    response_model=StandardSuccessResponse,
    summary="Get official Mixed Fleet Profile preset specification",
)
def get_mixed_fleet_preset_endpoint(
    service: MixedFleetService = Depends(get_mixed_fleet_service),
) -> StandardSuccessResponse:
    """Retrieve preconfigured capabilities and role allocation for Mixed Fleet template."""
    preset = service.get_preset_spec()
    return create_success_response(data=preset.model_dump())


@router.get(
    "/chats/{chat_id}/mixed-fleet/snapshot",
    response_model=StandardSuccessResponse,
    summary="Get fleet health snapshot and active task",
)
def get_fleet_snapshot_endpoint(
    chat_id: str = Path(..., min_length=1, description="Chat session ID"),
    service: MixedFleetService = Depends(get_mixed_fleet_service),
) -> StandardSuccessResponse:
    """Retrieve current availability of Local Brain, Remote Executor, and active handoffs."""
    snapshot = service.get_fleet_snapshot(chat_id=chat_id)
    return create_success_response(data=snapshot.model_dump())


@router.post(
    "/chats/{chat_id}/mixed-fleet/dispatch",
    response_model=StandardSuccessResponse,
    summary="Dispatch task from Local Brain to Remote Executor",
)
def dispatch_to_remote_endpoint(
    chat_id: str = Path(..., min_length=1, description="Chat session ID"),
    req: DispatchHandoffRequestSchema = ...,
    service: MixedFleetService = Depends(get_mixed_fleet_service),
) -> StandardSuccessResponse:
    """Compile structured handoff manifest and delegate to 24/7 Remote Executor."""
    try:
        manifest = service.dispatch_to_remote(chat_id=chat_id, request=req)
        return create_success_response(data=manifest.model_dump())
    except MixedFleetOfflineError as err:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(err),
        ) from err
    except MixedFleetError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err),
        ) from err


@router.post(
    "/chats/{chat_id}/mixed-fleet/{manifest_id}/sync",
    response_model=StandardSuccessResponse,
    summary="Sync remote executor progress back to Local Brain",
)
def sync_from_remote_endpoint(
    chat_id: str = Path(..., min_length=1, description="Chat session ID"),
    manifest_id: str = Path(..., min_length=1, description="Handoff manifest ID"),
    service: MixedFleetService = Depends(get_mixed_fleet_service),
) -> StandardSuccessResponse:
    """Pull latest results or execution output from Remote Executor."""
    try:
        manifest = service.sync_from_remote(chat_id=chat_id, manifest_id=manifest_id)
        return create_success_response(data=manifest.model_dump())
    except (MixedFleetHandoffNotFoundError, KeyError) as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(err),
        ) from err
    except MixedFleetError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err),
        ) from err


@router.post(
    "/chats/{chat_id}/mixed-fleet/{manifest_id}/complete",
    response_model=StandardSuccessResponse,
    summary="Mark remote execution completed",
)
def complete_remote_endpoint(
    chat_id: str = Path(..., min_length=1, description="Chat session ID"),
    manifest_id: str = Path(..., min_length=1, description="Handoff manifest ID"),
    req: CompleteRemoteExecutionRequestSchema = ...,
    service: MixedFleetService = Depends(get_mixed_fleet_service),
) -> StandardSuccessResponse:
    """Record completion summary from Remote Executor."""
    try:
        manifest = service.complete_remote_execution(
            chat_id=chat_id,
            manifest_id=manifest_id,
            output_summary=req.output_summary,
        )
        return create_success_response(data=manifest.model_dump())
    except (MixedFleetHandoffNotFoundError, KeyError) as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(err),
        ) from err


@router.post(
    "/chats/{chat_id}/mixed-fleet/{manifest_id}/fail",
    response_model=StandardSuccessResponse,
    summary="Mark remote execution failed",
)
def fail_remote_endpoint(
    chat_id: str = Path(..., min_length=1, description="Chat session ID"),
    manifest_id: str = Path(..., min_length=1, description="Handoff manifest ID"),
    req: FailRemoteExecutionRequestSchema = ...,
    service: MixedFleetService = Depends(get_mixed_fleet_service),
) -> StandardSuccessResponse:
    """Record execution failure details from Remote Executor."""
    try:
        manifest = service.fail_remote_execution(
            chat_id=chat_id,
            manifest_id=manifest_id,
            error_detail=req.error_detail,
        )
        return create_success_response(data=manifest.model_dump())
    except (MixedFleetHandoffNotFoundError, KeyError) as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(err),
        ) from err


@router.post(
    "/chats/{chat_id}/mixed-fleet/heartbeat",
    response_model=StandardSuccessResponse,
    summary="Update mixed fleet node heartbeat or availability",
)
def update_heartbeat_endpoint(
    chat_id: str = Path(..., min_length=1, description="Chat session ID"),
    req: UpdateFleetHeartbeatRequestSchema = ...,
    service: MixedFleetService = Depends(get_mixed_fleet_service),
) -> StandardSuccessResponse:
    """Update heartbeat timestamp and online flag for Local Brain or Remote Executor."""
    node = service.update_heartbeat(
        chat_id=chat_id,
        role=req.role,
        is_online=req.is_online,
    )
    return create_success_response(data=node.model_dump())
