"""[INPUT] MachineNode, MachineMetrics, RegistrationTokenResponse, and Takeover schemas.
[OUTPUT] REST API endpoints for self-hosted machine fleet management, telemetry heartbeats, and live takeover.
[POS] app/api/machines/router.py.
"""

from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query, status

from app.services.machines import (
    MachineMetrics,
    MachineNode,
    MachinePlatform,
    MachineService,
    RegistrationTokenResponse,
    TakeoverActionRequest,
    TakeoverSession,
)

router = APIRouter(prefix="/machines", tags=["machines"])


@router.get("", response_model=List[MachineNode])
def list_machines_endpoint() -> List[MachineNode]:
    """List all self-hosted machine nodes in the cluster with live metrics."""
    service = MachineService.get_instance()
    return service.list_machines()


@router.get("/{machine_id}", response_model=MachineNode)
def get_machine_endpoint(machine_id: str) -> MachineNode:
    """Get single self-hosted machine node details."""
    service = MachineService.get_instance()
    node = service.get_machine(machine_id)
    if not node:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Machine '{machine_id}' not found",
        )
    return node


@router.post(
    "/token",
    response_model=RegistrationTokenResponse,
    status_code=status.HTTP_201_CREATED,
)
def generate_registration_token_endpoint(
    platform: MachinePlatform = Query(
        MachinePlatform.DARWIN, description="Target host platform (darwin, linux, windows)"
    ),
) -> RegistrationTokenResponse:
    """Generate temporary registration token and copy-pasteable 1-click shell script."""
    service = MachineService.get_instance()
    return service.generate_registration_token(platform)


@router.post("/{machine_id}/heartbeat", response_model=MachineNode)
def report_heartbeat_endpoint(
    machine_id: str,
    metrics: MachineMetrics,
) -> MachineNode:
    """Report machine heartbeat with live CPU, memory, disk, and task telemetry."""
    service = MachineService.get_instance()
    return service.heartbeat(machine_id, metrics)


@router.post("/{machine_id}/takeover", response_model=TakeoverSession)
def initiate_takeover_endpoint(
    machine_id: str,
    payload: Optional[TakeoverActionRequest] = None,
) -> TakeoverSession:
    """Seize human control takeover on the remote machine screen."""
    service = MachineService.get_instance()
    node = service.get_machine(machine_id)
    if not node:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Machine '{machine_id}' not found",
        )

    operator_id = payload.operator_id if payload and payload.operator_id else "user-primary"
    return service.initiate_takeover(machine_id, operator_id)


@router.post("/{machine_id}/release", response_model=TakeoverSession)
def release_takeover_endpoint(
    machine_id: str,
) -> TakeoverSession:
    """Release human control and hand execution back to the autonomous agent."""
    service = MachineService.get_instance()
    node = service.get_machine(machine_id)
    if not node:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Machine '{machine_id}' not found",
        )

    return service.release_takeover(machine_id)


@router.get("/{machine_id}/takeover", response_model=Optional[TakeoverSession])
def get_takeover_session_endpoint(
    machine_id: str,
) -> Optional[TakeoverSession]:
    """Get active takeover session for a machine."""
    service = MachineService.get_instance()
    return service.get_takeover_session(machine_id)
