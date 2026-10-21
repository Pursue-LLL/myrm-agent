"""
[POS] app/api/agents/device_mesh_router.py
[INPUT] fastapi, app.schemas.device_mesh, app.services.agent.device_mesh_service
[OUTPUT] router

FastAPI router exposing edge device mesh node registration, pairing, heartbeats, and distributed command dispatch.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.schemas.device_mesh import (
    DeviceHeartbeatRequestDTO,
    DeviceNodeListResponseDTO,
    DispatchCommandRequestDTO,
    DispatchCommandResponseDTO,
    MeshDeviceNodeDTO,
    PairDeviceNodeRequestDTO,
    RegisterDeviceNodeRequestDTO,
)
from app.services.agent.device_mesh_service import (
    DeviceMeshService,
    get_device_mesh_service,
)

router = APIRouter()


@router.get(
    "/device-mesh/nodes",
    response_model=DeviceNodeListResponseDTO,
    status_code=status.HTTP_200_OK,
    summary="List all registered edge device mesh nodes",
)
def list_mesh_nodes(
    kind: str | None = Query(default=None, description="Filter by device kind (linux_server, mac_mini, etc.)"),
    status_filter: str | None = Query(default=None, alias="status", description="Filter by node status (online, offline, busy, unpaired)"),
    service: DeviceMeshService = Depends(get_device_mesh_service),
) -> DeviceNodeListResponseDTO:
    """Retrieve collection of registered edge device nodes in the mesh topology."""
    return service.list_nodes(kind=kind, status=status_filter)


@router.post(
    "/device-mesh/nodes",
    response_model=MeshDeviceNodeDTO,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new edge device node into the mesh",
)
def register_mesh_node(
    request: RegisterDeviceNodeRequestDTO,
    service: DeviceMeshService = Depends(get_device_mesh_service),
) -> MeshDeviceNodeDTO:
    """Register edge device hardware (Raspberry Pi, Mac Mini, GPU server, mobile testbed)."""
    return service.register_node(request)


@router.get(
    "/device-mesh/nodes/{node_id}",
    response_model=MeshDeviceNodeDTO,
    status_code=status.HTTP_200_OK,
    summary="Get details and telemetry of an edge device node",
)
def get_mesh_node(
    node_id: str,
    service: DeviceMeshService = Depends(get_device_mesh_service),
) -> MeshDeviceNodeDTO:
    """Fetch live status and telemetry of a specific edge node."""
    node = service.get_node(node_id)
    if node is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Edge device node '{node_id}' was not found.",
        )
    return node


@router.post(
    "/device-mesh/nodes/{node_id}/pair",
    response_model=MeshDeviceNodeDTO,
    status_code=status.HTTP_200_OK,
    summary="Pair an unpaired edge node with a verification token",
)
def pair_mesh_node(
    node_id: str,
    request: PairDeviceNodeRequestDTO,
    service: DeviceMeshService = Depends(get_device_mesh_service),
) -> MeshDeviceNodeDTO:
    """Verify pairing token and activate edge device connectivity."""
    try:
        return service.pair_node(node_id, request)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.post(
    "/device-mesh/nodes/{node_id}/heartbeat",
    response_model=MeshDeviceNodeDTO,
    status_code=status.HTTP_200_OK,
    summary="Report periodic heartbeat and telemetry from edge node",
)
def report_mesh_node_heartbeat(
    node_id: str,
    request: DeviceHeartbeatRequestDTO,
    service: DeviceMeshService = Depends(get_device_mesh_service),
) -> MeshDeviceNodeDTO:
    """Process heartbeat pulse from a connected edge hardware node."""
    try:
        return service.heartbeat(node_id, request)
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.post(
    "/device-mesh/dispatch",
    response_model=DispatchCommandResponseDTO,
    status_code=status.HTTP_200_OK,
    summary="Dispatch a command or workload task to an edge node",
)
def dispatch_command_to_node(
    request: DispatchCommandRequestDTO,
    service: DeviceMeshService = Depends(get_device_mesh_service),
) -> DispatchCommandResponseDTO:
    """Dispatch shell or diagnostic workload command to an edge node."""
    try:
        return service.dispatch_command(request)
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.delete(
    "/device-mesh/nodes/{node_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove an edge device node from the mesh",
)
def remove_mesh_node(
    node_id: str,
    service: DeviceMeshService = Depends(get_device_mesh_service),
) -> None:
    """Unregister and remove edge device from topology registry."""
    found = service.remove_node(node_id)
    if not found:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Edge device node '{node_id}' was not found.",
        )
