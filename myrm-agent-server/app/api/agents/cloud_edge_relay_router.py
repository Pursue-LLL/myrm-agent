"""FastAPI router for Hybrid Cloud-Edge Sandbox Relay & Artifact Sync (Item 58).

[INPUT]
- app.schemas.cloud_edge_relay::{
    RegisterArtifactRequest,
    AppendArtifactChunkRequest,
    DispatchLocalEgressRelayRequest,
    CompleteLocalEgressRelayRequest,
  }
- app.services.agent.cloud_edge_relay_service::{
    CloudEdgeRelayService,
    get_cloud_edge_relay_service,
  }

[OUTPUT]
- REST endpoints under /agents/cloud-edge-relay for cross-sandbox artifact synchronization
  and SSRF-safe local network egress relay dispatch.

[POS]
- HTTP API layer for Item 58 hybrid cloud-edge collaboration and network partition handling.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status

from app.schemas.cloud_edge_relay import (
    AppendArtifactChunkRequest,
    CompleteLocalEgressRelayRequest,
    DispatchLocalEgressRelayRequest,
    RegisterArtifactRequest,
)
from app.schemas.responses import StandardSuccessResponse, create_success_response
from app.services.agent.cloud_edge_relay_service import (
    CloudEdgeRelayService,
    get_cloud_edge_relay_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/agents/cloud-edge-relay",
    tags=["Subagent Cloud-Edge Relay & Artifact Sync"],
)


@router.post(
    "/artifacts/register",
    response_model=StandardSuccessResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a shared hybrid artifact with baseline content",
)
async def register_artifact(
    req: RegisterArtifactRequest,
    service: CloudEdgeRelayService = Depends(get_cloud_edge_relay_service),
) -> StandardSuccessResponse:
    """Initialize a synchronized artifact for bidirectional cloud/local sandbox append."""
    res = service.register_artifact(req)
    return create_success_response(data=res.model_dump())


@router.post(
    "/artifacts/append",
    response_model=StandardSuccessResponse,
    status_code=status.HTTP_200_OK,
    summary="Append an incremental chunk to a shared artifact",
)
async def append_artifact_chunk(
    req: AppendArtifactChunkRequest,
    service: CloudEdgeRelayService = Depends(get_cloud_edge_relay_service),
) -> StandardSuccessResponse:
    """Append content delta with optimistic CAS version verification."""
    try:
        res = service.append_chunk(req)
        return create_success_response(data=res.model_dump())
    except KeyError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(err),
        ) from err
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(err),
        ) from err


@router.get(
    "/artifacts",
    response_model=StandardSuccessResponse,
    status_code=status.HTTP_200_OK,
    summary="List all tracked hybrid artifacts",
)
async def list_artifacts(
    service: CloudEdgeRelayService = Depends(get_cloud_edge_relay_service),
) -> StandardSuccessResponse:
    """Retrieve metadata states for all active synchronized artifacts."""
    res = service.list_artifacts()
    return create_success_response(data=res.model_dump())


@router.get(
    "/artifacts/{artifact_id}",
    response_model=StandardSuccessResponse,
    status_code=status.HTTP_200_OK,
    summary="Get current snapshot state of an artifact",
)
async def get_artifact(
    artifact_id: str,
    service: CloudEdgeRelayService = Depends(get_cloud_edge_relay_service),
) -> StandardSuccessResponse:
    """Retrieve single artifact metadata and chunk summary."""
    try:
        state = service.get_artifact_state(artifact_id)
        return create_success_response(data=state.model_dump())
    except KeyError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Artifact '{artifact_id}' not found",
        ) from err


@router.get(
    "/artifacts/{artifact_id}/content",
    response_model=StandardSuccessResponse,
    status_code=status.HTTP_200_OK,
    summary="Get aggregated content across all chunks of an artifact",
)
async def get_artifact_content(
    artifact_id: str,
    service: CloudEdgeRelayService = Depends(get_cloud_edge_relay_service),
) -> StandardSuccessResponse:
    """Reconstruct full text of artifact from sequential chunks."""
    try:
        res = service.get_aggregated_content(artifact_id)
        return create_success_response(data=res.model_dump())
    except KeyError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Artifact '{artifact_id}' not found",
        ) from err


@router.get(
    "/artifacts/{artifact_id}/provenance",
    response_model=StandardSuccessResponse,
    status_code=status.HTTP_200_OK,
    summary="Get chronological provenance timeline of an artifact",
)
async def get_artifact_provenance(
    artifact_id: str,
    service: CloudEdgeRelayService = Depends(get_cloud_edge_relay_service),
) -> StandardSuccessResponse:
    """Retrieve audit provenance chain with author roles, timestamps, and checksums."""
    try:
        provenance = service.get_provenance_summary(artifact_id)
        return create_success_response(data={"artifact_id": artifact_id, "timeline": provenance})
    except KeyError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Artifact '{artifact_id}' not found",
        ) from err


@router.post(
    "/relay/dispatch",
    response_model=StandardSuccessResponse,
    status_code=status.HTTP_200_OK,
    summary="Dispatch outbound fetch relay through local network egress",
)
async def dispatch_egress_relay(
    req: DispatchLocalEgressRelayRequest,
    service: CloudEdgeRelayService = Depends(get_cloud_edge_relay_service),
) -> StandardSuccessResponse:
    """Execute or delegate web crawling via local network egress under SSRF guard."""
    try:
        res = service.dispatch_local_egress_relay(req)
        return create_success_response(data=res.model_dump())
    except (ValueError, PermissionError) as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"SSRF policy violation: {err}",
        ) from err


@router.post(
    "/relay/complete",
    response_model=StandardSuccessResponse,
    status_code=status.HTTP_200_OK,
    summary="Complete an asynchronous egress relay fetch task",
)
async def complete_egress_relay(
    req: CompleteLocalEgressRelayRequest,
    service: CloudEdgeRelayService = Depends(get_cloud_edge_relay_service),
) -> StandardSuccessResponse:
    """Report result of local egress crawl back to orchestrator."""
    res = service.complete_local_egress_relay(req)
    return create_success_response(data=res.model_dump())
