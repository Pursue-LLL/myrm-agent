from fastapi import APIRouter, HTTPException, status
from myrm_agent_harness.agent.sub_agents.fleet_router import (
    DuplicateGatewayError,
    GatewayNotFoundError,
    GatewayOfflineError,
)

from app.schemas.fleet_router import (
    BufferCommandRequest,
    BufferedCommandResponse,
    FleetProfileResponse,
    FleetTopologyResponse,
    FlushResponse,
    GatewayNodeResponse,
    HeartbeatRequest,
    InjectedContextResponse,
    RegisterGatewayRequest,
    RegisterProfileRequest,
    RelayArtifactRequest,
    RelayedArtifactResponse,
)
from app.services.agent.fleet_router_service import FleetRouterService

router = APIRouter(prefix="/fleet", tags=["Fleet Router"])


@router.get("/gateways", response_model=list[GatewayNodeResponse])
async def list_gateways() -> list[GatewayNodeResponse]:
    service = FleetRouterService.get_instance()
    return service.list_gateways()


@router.post("/gateways", response_model=GatewayNodeResponse, status_code=status.HTTP_201_CREATED)
async def register_gateway(req: RegisterGatewayRequest) -> GatewayNodeResponse:
    service = FleetRouterService.get_instance()
    try:
        return service.register_gateway(req)
    except DuplicateGatewayError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from e


@router.delete("/gateways/{gateway_id}")
async def unregister_gateway(gateway_id: str) -> dict[str, str]:
    service = FleetRouterService.get_instance()
    try:
        service.unregister_gateway(gateway_id)
        return {"status": "unregistered", "gateway_id": gateway_id}
    except GatewayNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e


@router.post("/gateways/{gateway_id}/heartbeat", response_model=GatewayNodeResponse)
async def update_heartbeat(gateway_id: str, req: HeartbeatRequest) -> GatewayNodeResponse:
    service = FleetRouterService.get_instance()
    try:
        return service.update_heartbeat(gateway_id, req)
    except GatewayNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e


@router.get("/profiles", response_model=list[FleetProfileResponse])
async def list_profiles() -> list[FleetProfileResponse]:
    service = FleetRouterService.get_instance()
    return service.list_profiles()


@router.post("/profiles", response_model=FleetProfileResponse, status_code=status.HTTP_201_CREATED)
async def register_profile(req: RegisterProfileRequest) -> FleetProfileResponse:
    service = FleetRouterService.get_instance()
    try:
        return service.register_profile(req)
    except GatewayNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e


@router.get("/profiles/{profile_id}/context", response_model=InjectedContextResponse)
async def get_injected_context(
    profile_id: str, base_context: str = ""
) -> InjectedContextResponse:
    service = FleetRouterService.get_instance()
    return service.get_injected_context(profile_id, base_context)


@router.post("/buffer", response_model=BufferedCommandResponse, status_code=status.HTTP_201_CREATED)
async def buffer_command(req: BufferCommandRequest) -> BufferedCommandResponse:
    service = FleetRouterService.get_instance()
    try:
        return service.buffer_command(req)
    except GatewayNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e


@router.post("/gateways/{gateway_id}/flush", response_model=FlushResponse)
async def flush_buffered_commands(gateway_id: str) -> FlushResponse:
    service = FleetRouterService.get_instance()
    try:
        return service.flush_buffered_commands(gateway_id)
    except GatewayNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except GatewayOfflineError as e:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e)) from e


@router.post("/relay", response_model=RelayedArtifactResponse, status_code=status.HTTP_201_CREATED)
async def relay_artifact(req: RelayArtifactRequest) -> RelayedArtifactResponse:
    service = FleetRouterService.get_instance()
    try:
        return service.relay_artifact(req)
    except GatewayNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e


@router.get("/topology", response_model=FleetTopologyResponse)
async def get_topology() -> FleetTopologyResponse:
    service = FleetRouterService.get_instance()
    return service.get_topology_snapshot()
