"""FastAPI router for Cross-Surface Agent Activity Conversation Bridge (Item 49).

[INPUT]
- app.schemas.cross_surface_bridge::{
    IngestActivityRequest,
    BatchIngestActivityRequest,
    PruneStalePresencesRequest,
  }
- app.services.agent.cross_surface_bridge_service::{
    CrossSurfaceBridgeService,
    cross_surface_bridge_service,
  }

[OUTPUT]
- REST endpoints under /chats/{chat_id}/activity-bridge for external activity ingress,
  bounded projection querying, and presence maintenance.

[POS]
- HTTP API layer for Cross-Surface Activity Bridge.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Path, status

from app.schemas.cross_surface_bridge import (
    BatchIngestActivityRequest,
    IngestActivityRequest,
    PruneStalePresencesRequest,
)
from app.schemas.responses import StandardSuccessResponse, create_success_response
from app.services.agent.cross_surface_bridge_service import (
    CrossSurfaceBridgeService,
    cross_surface_bridge_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Cross-Surface Agent Activity Bridge"])


def get_service() -> CrossSurfaceBridgeService:
    """Dependency injector for CrossSurfaceBridgeService."""
    return cross_surface_bridge_service


@router.post(
    "/chats/{chat_id}/activity-bridge/ingress",
    response_model=StandardSuccessResponse,
    status_code=status.HTTP_200_OK,
    summary="Ingress single external activity event from Tauri, CLI, or cron into Fleet Canvas",
)
def ingress_activity_endpoint(
    chat_id: str = Path(..., description="Unique chat session ID"),
    payload: IngestActivityRequest = ...,
    service: CrossSurfaceBridgeService = Depends(get_service),
) -> StandardSuccessResponse:
    """Ingresses an external agent event and updates the bounded projection state."""
    snapshot = service.ingest_activity(chat_id=chat_id, request=payload)
    return create_success_response(data=snapshot.model_dump())


@router.post(
    "/chats/{chat_id}/activity-bridge/ingress-batch",
    response_model=StandardSuccessResponse,
    status_code=status.HTTP_200_OK,
    summary="Batch ingress external activity events from an external pipeline",
)
def ingress_batch_endpoint(
    chat_id: str = Path(..., description="Unique chat session ID"),
    payload: BatchIngestActivityRequest = ...,
    service: CrossSurfaceBridgeService = Depends(get_service),
) -> StandardSuccessResponse:
    """Batch ingresses external events into the bounded projection waterfall."""
    snapshot = service.ingest_batch(chat_id=chat_id, request=payload)
    return create_success_response(data=snapshot.model_dump())


@router.get(
    "/chats/{chat_id}/activity-bridge/projection",
    response_model=StandardSuccessResponse,
    summary="Get bounded activity waterfall and active external presences for Fleet Canvas",
)
def get_projection_endpoint(
    chat_id: str = Path(..., description="Unique chat session ID"),
    service: CrossSurfaceBridgeService = Depends(get_service),
) -> StandardSuccessResponse:
    """Retrieves current external activities and presence states without loading full transcripts."""
    snapshot = service.get_projection_snapshot(chat_id=chat_id)
    return create_success_response(data=snapshot.model_dump())


@router.post(
    "/chats/{chat_id}/activity-bridge/prune-stale",
    response_model=StandardSuccessResponse,
    status_code=status.HTTP_200_OK,
    summary="Prune idle or completed external surface presences",
)
def prune_stale_endpoint(
    chat_id: str = Path(..., description="Unique chat session ID"),
    payload: PruneStalePresencesRequest = ...,
    service: CrossSurfaceBridgeService = Depends(get_service),
) -> StandardSuccessResponse:
    """Marks inactive sessions as idle and prunes expired completed sessions."""
    result = service.prune_stale(chat_id=chat_id, request=payload)
    return create_success_response(data=result.model_dump())


@router.post(
    "/chats/{chat_id}/activity-bridge/reset",
    response_model=StandardSuccessResponse,
    summary="Reset external activity projection buffer for session",
)
def reset_session_endpoint(
    chat_id: str = Path(..., description="Unique chat session ID"),
    service: CrossSurfaceBridgeService = Depends(get_service),
) -> StandardSuccessResponse:
    """Clears all external events and presences for the session."""
    snapshot = service.reset_session(chat_id=chat_id)
    return create_success_response(data=snapshot.model_dump())
