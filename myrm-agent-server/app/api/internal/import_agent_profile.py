"""Control Plane → sandbox Agent profile import endpoint.

[INPUT]
- services.agent.marketplace.import_::import_agent_package (POS: Server-side marketplace import)
- services.agent.profile_snapshot_service::ProfileSnapshotService (POS: 快照服务)
- database.repositories.uow::UnitOfWork (POS: Unit of Work 事务层)

[OUTPUT]
- POST /api/admin/import-agent-profile: Import or force-update Agent from marketplace package

[POS]
CP-to-sandbox internal endpoint for marketplace Agent installation and force-push updates.
Receives a serialized Agent package, enforces contract/integrity + optional CP transport
signature verification, then creates/updates the Agent + dependencies locally.
When `force=True`, snapshots the existing Agent before overwriting so the user can rollback.
"""

from __future__ import annotations

import logging
import os
import secrets

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.core.memory.adapters.policy import memory_policy_from_dict
from app.database.repositories.uow import UnitOfWork
from app.services.agent.marketplace import import_agent_package, validate_marketplace_package

logger = logging.getLogger(__name__)
router = APIRouter()

_CP_TOKEN_ENV = "CONTROL_PLANE_TELEMETRY_TOKEN"
_CP_TOKEN_HEADER = "X-Telemetry-Token"
_MARKETPLACE_SIGN_SECRET_ENV = "MARKETPLACE_CP_SIGNING_SECRET"
_MARKETPLACE_REQUIRE_SIGNATURE_ENV = "MARKETPLACE_REQUIRE_CP_SIGNATURE"
_MARKETPLACE_ENTRY_ENGINE_PARAM_KEY = "marketplace_entry_id"


class ImportAgentProfileRequest(BaseModel):
    package: dict
    force: bool = False
    target_agent_id: str | None = None
    marketplace_entry_id: str | None = None


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


def _env_flag(value: str | None, *, default: bool) -> bool:
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


def _marketplace_signature_policy() -> tuple[bool, str | None]:
    secret_raw = os.environ.get(_MARKETPLACE_SIGN_SECRET_ENV)
    secret = secret_raw.strip() if isinstance(secret_raw, str) else ""
    normalized_secret = secret or None
    require_signature = _env_flag(
        os.environ.get(_MARKETPLACE_REQUIRE_SIGNATURE_ENV),
        default=normalized_secret is not None,
    )
    return require_signature, normalized_secret


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

        require_signature, signature_secret = _marketplace_signature_policy()
        normalized_entry_id = _normalize_marketplace_entry_id(body.marketplace_entry_id)
        validated_package = validate_marketplace_package(
            body.package,
            require_transport_signature=require_signature,
            transport_secret=signature_secret,
        )
        normalized_package = validated_package.model_dump()

        if body.force:
            target_id = body.target_agent_id
            if isinstance(target_id, str):
                target_id = target_id.strip() or None
            if not target_id:
                if normalized_entry_id is None:
                    raise HTTPException(
                        status_code=400,
                        detail=(
                            "Force-push import requires marketplace_entry_id binding "
                            "or explicit target_agent_id"
                        ),
                    )
                target_id = await _resolve_force_push_agent_id(normalized_entry_id)
            if not target_id:
                raise HTTPException(
                    status_code=404,
                    detail=(
                        "Installed marketplace agent binding not found for force-push "
                        f"(marketplace_entry_id={normalized_entry_id}). "
                        "Please reinstall this marketplace entry in the sandbox."
                    ),
                )
            return await _force_update_agent(
                target_id,
                normalized_package,
                marketplace_entry_id=normalized_entry_id,
            )

        agent_id = await import_agent_package(
            skill_creation_service,
            normalized_package,
            require_transport_signature=require_signature,
            transport_secret=signature_secret,
            marketplace_entry_id=normalized_entry_id,
        )
        return ImportAgentProfileResponse(agent_id=agent_id, status="installed")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        logger.exception("Failed to import agent profile from marketplace")
        raise HTTPException(status_code=500, detail="Import failed")


def _normalize_marketplace_entry_id(entry_id: str | None) -> str | None:
    if entry_id is None:
        return None
    normalized = entry_id.strip()
    if not normalized:
        raise HTTPException(
            status_code=400,
            detail="marketplace_entry_id must be a non-empty string",
        )
    return normalized


async def _resolve_force_push_agent_id(marketplace_entry_id: str) -> str | None:
    """Resolve force-push target by stable marketplace entry binding."""
    async with UnitOfWork() as uow:
        profiles = await uow.agent_repo.list_profiles()

    matched_ids: list[str] = []
    for profile in profiles:
        metadata = profile.metadata
        if not isinstance(metadata, dict):
            continue
        engine_params = metadata.get("engine_params")
        if not isinstance(engine_params, dict):
            continue
        bound_entry_id = engine_params.get(_MARKETPLACE_ENTRY_ENGINE_PARAM_KEY)
        if isinstance(bound_entry_id, str) and bound_entry_id == marketplace_entry_id:
            matched_ids.append(profile.id)

    if not matched_ids:
        return None
    if len(matched_ids) > 1:
        raise HTTPException(
            status_code=409,
            detail=(
                "Force-push target is ambiguous: multiple local agents are bound to "
                f"marketplace_entry_id={marketplace_entry_id}. "
                "Please set target_agent_id explicitly."
            ),
        )
    return matched_ids[0]


def _extract_model_update(profile_data: dict[str, object]) -> tuple[str | None, dict[str, object] | None]:
    model_selection = profile_data.get("model_selection")
    if isinstance(model_selection, dict):
        model = model_selection.get("model")
        if isinstance(model, str) and model.strip():
            return model.strip(), model_selection
    model_value = profile_data.get("model")
    if isinstance(model_value, str) and model_value.strip():
        model_name = model_value.strip()
        return model_name, {"providerId": "auto", "model": model_name}
    return None, None


async def _force_update_agent(
    agent_id: str,
    package: dict,
    *,
    marketplace_entry_id: str | None = None,
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

    profile_data_raw = package.get("agent_profile", {})
    profile_data = profile_data_raw if isinstance(profile_data_raw, dict) else {}
    updates: dict[str, object] = {}
    for key in (
        "display_name",
        "description",
        "system_prompt",
        "max_iterations",
        "personality_style",
    ):
        if key in profile_data:
            updates[key] = profile_data[key]

    model_name, model_selection = _extract_model_update(profile_data)
    if model_name is not None:
        updates["model"] = model_name
    if model_selection is not None:
        updates["model_selection"] = model_selection

    if "skill_ids" in profile_data:
        updates["skills"] = profile_data["skill_ids"]
    if "skill_configs" in profile_data:
        updates["skill_configs"] = profile_data["skill_configs"]
    if "memory_policy" in profile_data:
        raw_memory_policy = profile_data["memory_policy"]
        updates["memory_policy"] = (
            memory_policy_from_dict(raw_memory_policy)
            if isinstance(raw_memory_policy, dict)
            else None
        )
    if "command_bindings" in profile_data:
        updates["command_bindings"] = profile_data["command_bindings"]
    if "workspace_policy" in profile_data:
        updates["workspace_policy"] = profile_data["workspace_policy"]
    if "cron_post_run_verify" in profile_data:
        updates["cron_post_run_verify"] = bool(profile_data["cron_post_run_verify"])
    if "enabled_builtin_tools" in profile_data:
        from app.services.agent.builtin_tool_ids import normalize_enabled_builtin_tools

        updates["tools_allowed"] = normalize_enabled_builtin_tools(
            profile_data["enabled_builtin_tools"]
        )

    metadata_keys = (
        "mcp_ids",
        "mcp_tool_selections",
        "subagent_ids",
        "security_overrides",
        "engine_params",
        "auto_restore_domains",
        "openapi_services",
        "workspace_policy",
        "prompt_mode",
        "suggestion_prompts",
        "agent_type",
        "session_policy",
        "notify_targets",
        "browser_source",
        "dialog_policy",
        "session_recording",
    )
    meta_update: dict[str, object] = {}
    for mk in metadata_keys:
        if mk in profile_data:
            meta_update[mk] = profile_data[mk]
    if marketplace_entry_id is not None:
        meta_update["engine_params"] = _with_marketplace_entry_binding(
            meta_update.get("engine_params"),
            marketplace_entry_id,
        )
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


def _with_marketplace_entry_binding(
    engine_params: object,
    marketplace_entry_id: str,
) -> dict[str, object]:
    merged: dict[str, object] = (
        dict(engine_params)
        if isinstance(engine_params, dict)
        else {}
    )
    merged[_MARKETPLACE_ENTRY_ENGINE_PARAM_KEY] = marketplace_entry_id
    return merged
