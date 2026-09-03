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
    agent_id: str = "default"
    expose_desktop: bool = False


class GenerateConfigResponse(BaseModel):
    profile_id: str
    agent_id: str
    mcp_url: str
    token: str
    config_json: dict[str, object]
    instructions: str
    expose_desktop: bool = False
    desktop_tools: list[str] = []


class DoctorRequest(BaseModel):
    profile_id: str


class DoctorResponse(BaseModel):
    profile_id: str
    healthy: bool
    detail: str = "unknown"
    severity: str = "error"


class RevokeRequest(BaseModel):
    profile_id: str
    clear_synced_memory: bool = False


class RevokeResponse(BaseModel):
    profile_id: str
    revoked: bool
    trees_removed: int = 0


class AgentPluginRequest(BaseModel):
    agent_id: str = "default"
    embed_token: bool = False


class AgentPluginResponse(BaseModel):
    agent_id: str
    mcp_url: str
    token: str
    embed_token: bool
    files: dict[str, str]
    instructions: str


class ConnectorStatusResponse(BaseModel):
    profile_id: str
    label: str
    status: str
    agent_id: str
    doctor_ok: bool
    last_doctor_detail: str = ""
    connected_at: str | None
    last_doctor_at: str | None
    expose_desktop: bool = False


class AgentConnectCapabilityResponse(BaseModel):
    agent_id: str
    has_computer_use: bool
    desktop_deploy_supported: bool
    can_expose_desktop: bool


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
        snippet = await service.generate_config(
            body.profile_id,
            agent_id=body.agent_id,
            expose_desktop=body.expose_desktop,
        )
    except ValueError as e:
        from fastapi import HTTPException

        raise HTTPException(status_code=400, detail=str(e)) from e
    desktop_tools = (
        ["desktop_snapshot_tool", "desktop_interact_tool", "desktop_vision_tool"]
        if snippet.expose_desktop
        else []
    )
    return GenerateConfigResponse(
        profile_id=snippet.profile_id,
        agent_id=snippet.agent_id,
        mcp_url=snippet.mcp_url,
        token=snippet.token,
        config_json=snippet.config_json,
        instructions=snippet.instructions,
        expose_desktop=snippet.expose_desktop,
        desktop_tools=desktop_tools,
    )


@router.post("/connect/doctor")
async def run_doctor(body: DoctorRequest) -> DoctorResponse:
    """Run health check on a connector."""
    service = get_connect_service()
    result = await service.doctor(body.profile_id)
    return DoctorResponse(
        profile_id=body.profile_id,
        healthy=result.healthy,
        detail=result.detail,
        severity=result.severity,
    )


@router.post("/connect/agent-plugin")
async def generate_agent_plugin(body: AgentPluginRequest) -> AgentPluginResponse:
    """Generate a portable Agent Plugins 1.0.0 bundle exposing Myrm memory."""
    service = get_connect_service()
    bundle = await service.generate_agent_plugin_bundle(agent_id=body.agent_id, embed_token=body.embed_token)
    return AgentPluginResponse(
        agent_id=bundle.agent_id,
        mcp_url=bundle.mcp_url,
        token=bundle.token,
        embed_token=bundle.embed_token,
        files=bundle.files,
        instructions=bundle.instructions,
    )


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
        from app.services.memory.imports.integration_memory import get_integration_memory_service

        svc = await get_integration_memory_service()
        if svc:
            trees_removed = await svc.remove_trees_by_provider(body.profile_id)

    return RevokeResponse(profile_id=body.profile_id, revoked=revoked, trees_removed=trees_removed)


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
            agent_id=s.agent_id,
            doctor_ok=s.doctor_ok,
            last_doctor_detail=s.last_doctor_detail,
            connected_at=s.connected_at.isoformat() if s.connected_at else None,
            last_doctor_at=s.last_doctor_at.isoformat() if s.last_doctor_at else None,
            expose_desktop=s.expose_desktop,
        )
        for s in states
    ]


@router.get("/connect/agent-capabilities/{agent_id}")
async def get_agent_connect_capabilities(agent_id: str) -> AgentConnectCapabilityResponse:
    """Inspect whether an Agent Profile can expose desktop control tools via MCP."""
    from app.config.computer_use_deploy import is_computer_use_deploy_supported
    from app.services.agent.profile.profile_resolver import (
        get_agent_profile_resolver,
        resolve_builtin_tool_flags,
    )

    deploy_supported = is_computer_use_deploy_supported()
    resolver = get_agent_profile_resolver()
    profile = await resolver.resolve(agent_id)
    has_computer_use = False
    if profile is not None:
        flags = resolve_builtin_tool_flags(profile.enabled_builtin_tools)
        has_computer_use = bool(flags.get("enable_computer_use"))

    can_expose_desktop = has_computer_use and deploy_supported
    return AgentConnectCapabilityResponse(
        agent_id=agent_id,
        has_computer_use=has_computer_use,
        desktop_deploy_supported=deploy_supported,
        can_expose_desktop=can_expose_desktop,
    )
