"""FastAPI router for external agent skill bridge and unified memory gateway.

[POS]
app/api/memory/external_bridge.py
Exposes endpoints for external tool discovery, idempotent instruction injection/uninstallation,
sub-20ms memory queries, and security-verified fact contributions.

[INPUT]
- app.schemas.external_skill_bridge DTOs
- app.services.memory.skill_bridge::get_external_skill_bridge_service

[OUTPUT]
- router: APIRouter for external agent skill installation and memory gateway
"""

from __future__ import annotations

from fastapi import APIRouter, Query

from app.schemas.external_skill_bridge import (
    ExternalMemoryContributeRequest,
    ExternalMemoryContributeResponse,
    ExternalMemoryQueryRequest,
    ExternalMemoryQueryResponse,
    ExternalTargetsListResponse,
    InstallSkillBridgeRequest,
    InstallSkillBridgeResponse,
    UninstallSkillBridgeRequest,
    UninstallSkillBridgeResponse,
)
from app.services.memory.skill_bridge import get_external_skill_bridge_service

router = APIRouter(prefix="/external", tags=["memory-external-skill-bridge"])


@router.get(
    "/targets",
    response_model=ExternalTargetsListResponse,
    summary="List all supported external agent targets and local configuration status",
)
def list_targets(
    workspace_root: str | None = Query(default=None, description="Workspace directory to probe"),
    global_config: bool = Query(default=False, description="Probe global user home directory"),
) -> ExternalTargetsListResponse:
    """Scan and list supported external agent integration targets."""
    service = get_external_skill_bridge_service()
    return service.list_supported_targets(
        workspace_root=workspace_root,
        global_config=global_config,
    )


@router.post(
    "/install",
    response_model=InstallSkillBridgeResponse,
    summary="Install or update memory bridge instructions in external agent configuration",
)
def install_bridge(request: InstallSkillBridgeRequest) -> InstallSkillBridgeResponse:
    """Atomically install or update delimiter-isolated instructions."""
    service = get_external_skill_bridge_service()
    return service.install_bridge(request)


@router.post(
    "/uninstall",
    response_model=UninstallSkillBridgeResponse,
    summary="Uninstall memory bridge instructions from external agent configuration",
)
def uninstall_bridge(request: UninstallSkillBridgeRequest) -> UninstallSkillBridgeResponse:
    """Safely strip delimiter-isolated instructions while preserving other configurations."""
    service = get_external_skill_bridge_service()
    return service.uninstall_bridge(request)


@router.post(
    "/query",
    response_model=ExternalMemoryQueryResponse,
    summary="Low-latency memory recall endpoint for external agents and CLI tools",
)
def query_memory(request: ExternalMemoryQueryRequest) -> ExternalMemoryQueryResponse:
    """Fast memory recall for external agent coding sessions (<20ms)."""
    service = get_external_skill_bridge_service()
    return service.query_external_memory(request)


@router.post(
    "/contribute",
    response_model=ExternalMemoryContributeResponse,
    summary="Sanitize and store new factual insight contributed by external agent",
)
def contribute_memory(request: ExternalMemoryContributeRequest) -> ExternalMemoryContributeResponse:
    """Sanitize and store factual insight contributed by external agent."""
    service = get_external_skill_bridge_service()
    return service.contribute_external_memory(request)
