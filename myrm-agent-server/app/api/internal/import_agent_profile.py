"""Control Plane → sandbox Agent profile import endpoint.

[INPUT]
- services.agent.marketplace_import::import_agent_package (POS: Server-side marketplace import)
- services.agent.profile_snapshot_service::ProfileSnapshotService (POS: 快照服务)
- database.repositories.uow::UnitOfWork (POS: Unit of Work 事务层)

[OUTPUT]
- POST /api/admin/import-agent-profile: Import or force-update Agent from marketplace package

[POS]
CP-to-sandbox internal endpoint for marketplace Agent installation and force-push updates.
Receives a serialized Agent package and creates/updates the Agent + dependencies locally.
When `force=True`, snapshots the existing Agent before overwriting so the user can rollback.
"""

from __future__ import annotations

import logging
import os
import secrets

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.database.repositories.uow import UnitOfWork
from app.services.agent.marketplace_import import import_agent_package

logger = logging.getLogger(__name__)
router = APIRouter()

_CP_TOKEN_ENV = "CONTROL_PLANE_TELEMETRY_TOKEN"
_CP_TOKEN_HEADER = "X-Telemetry-Token"


class ImportAgentProfileRequest(BaseModel):
    package: dict
    force: bool = False
    target_agent_id: str | None = None


class ImportAgentProfileResponse(BaseModel):
    agent_id: str
    status: str = "installed"
    snapshot_id: str | None = None


def _verify_cp_token(request: Request) -> None:
    """Verify the request comes from the Control Plane."""
    expected = os.environ.get(_CP_TOKEN_ENV)
    if not expected:
        return
    provided = request.headers.get(_CP_TOKEN_HEADER, "")
    if not secrets.compare_digest(provided, expected):
        raise HTTPException(status_code=403, detail="Invalid CP token")


@router.post(
    "/api/admin/import-agent-profile",
    response_model=ImportAgentProfileResponse,
)
async def import_agent_profile_endpoint(
    body: ImportAgentProfileRequest,
    request: Request,
):
    """Import an Agent profile package from the marketplace.

    Called by the Control Plane during marketplace install to push
    Agent configuration into the user's sandbox.

    When ``force=True``, the endpoint snapshots the existing Agent before
    overwriting, enabling user rollback via the snapshot service.
    """
    _verify_cp_token(request)

    try:
        from app.core.skills.creation.service import skill_creation_service

        if body.force and body.target_agent_id:
            return await _force_update_agent(
                body.target_agent_id, body.package,
            )

        agent_id = await import_agent_package(skill_creation_service, body.package)
        return ImportAgentProfileResponse(agent_id=agent_id, status="installed")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        logger.exception("Failed to import agent profile from marketplace")
        raise HTTPException(status_code=500, detail="Import failed")


async def _force_update_agent(
    agent_id: str,
    package: dict,
) -> ImportAgentProfileResponse:
    """Snapshot existing Agent then overwrite with the marketplace package."""
    from app.services.agent.agent_service import AgentService
    from app.services.agent.profile_snapshot_service import ProfileSnapshotService
    from app.services.event.app_event_bus import AppEvent, AppEventType, get_event_bus

    existing = await AgentService.get_agent(agent_id)
    if not existing:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")

    snapshot_id = await ProfileSnapshotService.save_profile_snapshot(
        agent_id, reason="pre-force-push",
    )
    logger.info("Pre-force-push snapshot %s for agent %s", snapshot_id, agent_id)

    profile_data: dict = package.get("agent_profile", {})
    updates: dict[str, object] = {}
    for key in ("display_name", "description", "system_prompt", "model",
                "max_iterations", "personality_style"):
        if key in profile_data:
            updates[key] = profile_data[key]

    if "skill_ids" in profile_data:
        updates["skills"] = profile_data["skill_ids"]
    if "skill_configs" in profile_data:
        updates["skill_configs"] = profile_data["skill_configs"]
    if "enabled_builtin_tools" in profile_data:
        updates["tools_allowed"] = profile_data["enabled_builtin_tools"]

    metadata_keys = (
        "mcp_ids", "mcp_tool_selections", "subagent_ids",
        "security_overrides", "engine_params", "auto_restore_domains",
        "openapi_services", "workspace_policy", "model_selection",
    )
    meta_update: dict[str, object] = {}
    for mk in metadata_keys:
        if mk in profile_data:
            meta_update[mk] = profile_data[mk]
    if meta_update:
        updates["metadata"] = meta_update

    if updates:
        async with UnitOfWork() as uow:
            repo = uow.agent_repo
            await repo.update_profile(agent_id, updates)
            await uow.commit()

    get_event_bus().publish(AppEvent(
        event_type=AppEventType.AGENT_CONFIG_UPDATED,
        data={"agent_id": agent_id, "action": "force_push", "snapshot_id": snapshot_id},
    ))

    return ImportAgentProfileResponse(
        agent_id=agent_id,
        status="force_updated",
        snapshot_id=snapshot_id,
    )
