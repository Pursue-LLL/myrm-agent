"""Connect Wizard API: manage external agent connections.

[INPUT]
- app.services.connect::ConnectService (POS: Connection management service)

[OUTPUT]
- router: FastAPI router for /connect endpoints

[POS]
REST API for the Connect Wizard feature. Allows frontend to:
- List supported external agent profiles
- Generate MCP config snippets + tokens
- Run doctor checks on connections
- Revoke connections
- Get overall connector status
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.services.connect import ConnectorStatus, get_connect_service

router = APIRouter()


class ProfileResponse(BaseModel):
    id: str
    label: str
    description: str
    config_file_path: str
    status: str


class GenerateConfigRequest(BaseModel):
    profile_id: str


class GenerateConfigResponse(BaseModel):
    profile_id: str
    mcp_url: str
    token: str
    config_json: dict[str, object]
    instructions: str


class DoctorRequest(BaseModel):
    profile_id: str


class DoctorResponse(BaseModel):
    profile_id: str
    healthy: bool


class RevokeRequest(BaseModel):
    profile_id: str
    clear_synced_memory: bool = False


class RevokeResponse(BaseModel):
    profile_id: str
    revoked: bool
    trees_removed: int = 0


class ConnectorStatusResponse(BaseModel):
    profile_id: str
    label: str
    status: str
    doctor_ok: bool
    connected_at: str | None


@router.get("/connect/profiles")
async def list_profiles() -> list[ProfileResponse]:
    """List all supported external agent connection profiles."""
    service = get_connect_service()
    profiles = service.list_profiles()
    states = {s.profile_id: s for s in service.list_all_states()}
    return [
        ProfileResponse(
            id=p.id,
            label=p.label,
            description=p.description,
            config_file_path=p.config_file_path,
            status=states[p.id].status.value if p.id in states else ConnectorStatus.MISSING.value,
        )
        for p in profiles
    ]


@router.post("/connect/generate")
async def generate_config(body: GenerateConfigRequest) -> GenerateConfigResponse:
    """Generate MCP config and token for an external agent."""
    service = get_connect_service()
    try:
        snippet = await service.generate_config(body.profile_id)
    except ValueError as e:
        from fastapi import HTTPException

        raise HTTPException(status_code=400, detail=str(e)) from e
    return GenerateConfigResponse(
        profile_id=snippet.profile_id,
        mcp_url=snippet.mcp_url,
        token=snippet.token,
        config_json=snippet.config_json,
        instructions=snippet.instructions,
    )


@router.post("/connect/doctor")
async def run_doctor(body: DoctorRequest) -> DoctorResponse:
    """Run health check on a connector."""
    service = get_connect_service()
    healthy = await service.doctor(body.profile_id)
    return DoctorResponse(profile_id=body.profile_id, healthy=healthy)


@router.post("/connect/revoke")
async def revoke_connector(body: RevokeRequest) -> RevokeResponse:
    """Revoke a connector's token and disconnect.

    If clear_synced_memory is True, also removes all integration memory trees
    synced via this connector's provider.
    """
    service = get_connect_service()
    revoked = service.revoke(body.profile_id)

    trees_removed = 0
    if body.clear_synced_memory and revoked:
        from app.services.memory.integration_memory import get_integration_memory_service

        svc = await get_integration_memory_service()
        if svc:
            trees_removed = await svc.remove_trees_by_provider(body.profile_id)

    return RevokeResponse(
        profile_id=body.profile_id, revoked=revoked, trees_removed=trees_removed
    )


@router.get("/connect/status")
async def list_connector_status() -> list[ConnectorStatusResponse]:
    """Get status of all connectors."""
    service = get_connect_service()
    profiles = {p.id: p for p in service.list_profiles()}
    states = service.list_all_states()
    return [
        ConnectorStatusResponse(
            profile_id=s.profile_id,
            label=profiles[s.profile_id].label if s.profile_id in profiles else s.profile_id,
            status=s.status.value,
            doctor_ok=s.doctor_ok,
            connected_at=s.connected_at.isoformat() if s.connected_at else None,
        )
        for s in states
    ]
