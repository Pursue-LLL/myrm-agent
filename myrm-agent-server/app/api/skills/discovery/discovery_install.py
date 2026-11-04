"""Skill discovery install/update/uninstall endpoints.

[INPUT]
app.api.skills.discovery.discovery_schemas (POS: Request/response Pydantic models)
app.api.skills._deploy_capability::require_local_skills_capability (POS: Local-mode gate)
app.core.skills.audit::audit_skill_action (POS: Skill action audit logging)
app.core.skills.discovery.adopt::complete_discovery_adoption (POS: Explicit allowlist append after install)
app.core.skills.discovery.autoupdate::get_update_checker (POS: Remote version lookup and quarantine update flow)
app.core.skills.discovery.mount::maybe_mount_after_install (POS: Post-install user catalog enable)
app.core.skills.marketplace.market_service::market_service (POS: Skill search/install orchestrator)

[OUTPUT]
router: FastAPI router with install, update, uninstall, URL analysis and URL install endpoints.

[POS]
Skill discovery write paths. Kept apart from read-only discovery so each router stays small
and the install response shape has one owner.
"""

import logging
from typing import cast

from fastapi import APIRouter, HTTPException
from myrm_agent_harness.agent.skills.market.service import BaseSkillMarketService
from myrm_agent_harness.api.skills import SkillInstallResult

from app.api.skills._deploy_capability import require_local_skills_capability
from app.api.skills.discovery.discovery_schemas import (
    SkillAnalyzeUrlResponse,
    SkillInstallFromUrlRequest,
    SkillInstallRequest,
    SkillInstallResponse,
    SkillReceiptResponse,
    SkillUninstallRequest,
    SkillUpdateRequest,
    SkillUrlInfo,
)
from app.core.skills.audit import audit_skill_action as _audit_skill_action
from app.core.skills.discovery.adopt import complete_discovery_adoption
from app.core.skills.discovery.autoupdate import get_update_checker
from app.core.skills.discovery.mount import (
    SkillMountResult,
    maybe_mount_after_install,
    resolve_mount_skill_id,
)
from app.core.skills.marketplace.market_service import market_service

logger = logging.getLogger(__name__)

router = APIRouter()


def _discovery_framework(svc: object) -> BaseSkillMarketService:
    return cast(BaseSkillMarketService, svc._base)  # type: ignore[attr-defined]


def _install_response(
    result: SkillInstallResult,
    *,
    mount_result: SkillMountResult | None = None,
    allowlist_appended: bool = False,
    allowlist_append_error: str = "",
    pre_replace_batch_id: str | None = None,
    snapshot_truncated: bool = False,
) -> SkillInstallResponse:
    response_skill_id = resolve_mount_skill_id(result) or result.skill_id
    mounted = False
    mount_agent_id = ""
    mount_skill_id = ""
    mount_already_present = False
    mount_error = ""

    if mount_result is not None:
        mounted = mount_result.mounted
        mount_agent_id = mount_result.agent_id
        mount_skill_id = mount_result.mount_skill_id
        mount_already_present = mount_result.already_mounted
        mount_error = mount_result.error

    receipt_resp: SkillReceiptResponse | None = None
    if result.receipt is not None:
        receipt_resp = SkillReceiptResponse(
            receipt_id=result.receipt.receipt_id,
            skill_id=result.receipt.skill_id,
            skill_name=result.receipt.skill_name,
            source=result.receipt.source,
            installed_at=result.receipt.installed_at,
            version=result.receipt.version,
            installed_path=result.receipt.installed_path,
            installed_skills=list(result.receipt.installed_skills),
            declared_mcp_servers=list(result.receipt.declared_mcp_servers),
            scan_score=result.receipt.scan_score,
            security_verified=result.receipt.security_verified,
            manifest_hash=result.receipt.manifest_hash,
        )

    return SkillInstallResponse(
        success=result.success,
        skill_name=result.skill_name,
        skill_id=response_skill_id,
        installed_path=result.installed_path,
        error=result.error,
        error_code=result.error_code,
        mounted=mounted,
        mount_agent_id=mount_agent_id,
        mount_skill_id=mount_skill_id,
        mount_already_present=mount_already_present,
        mount_error=mount_error,
        allowlist_appended=allowlist_appended,
        allowlist_append_error=allowlist_append_error,
        installed_skills=list(result.installed_skills),
        declared_mcp_servers=list(result.declared_mcp_servers),
        receipt=receipt_resp,
        pre_replace_batch_id=pre_replace_batch_id,
        snapshot_truncated=snapshot_truncated,
    )


async def _install_response_with_adoption(
    result: SkillInstallResult,
    *,
    mount_result: SkillMountResult | None = None,
    pre_replace_batch_id: str | None = None,
    snapshot_truncated: bool = False,
) -> SkillInstallResponse:
    allowlist_appended = False
    allowlist_append_error = ""
    if mount_result is not None and mount_result.mounted and mount_result.mount_skill_id and mount_result.agent_id:
        adoption = await complete_discovery_adoption(
            mount_result.agent_id,
            mount_result.mount_skill_id,
        )
        allowlist_appended = adoption.allowlist_appended
        allowlist_append_error = adoption.allowlist_append_error

    return _install_response(
        result,
        mount_result=mount_result,
        allowlist_appended=allowlist_appended,
        allowlist_append_error=allowlist_append_error,
        pre_replace_batch_id=pre_replace_batch_id,
        snapshot_truncated=snapshot_truncated,
    )


@router.post("/install", response_model=SkillInstallResponse)
async def install_skill(
    request: SkillInstallRequest,
) -> SkillInstallResponse:
    """Install a skill from external source to local filesystem."""
    require_local_skills_capability()
    from app.core.skills.discovery.market_install_flow import run_market_install_flow_by_id

    flow = await run_market_install_flow_by_id(
        request.skill_id,
        request.source,
        allow_downgrade=request.allow_downgrade,
        agent_id=request.agent_id,
        mount_to_agent=request.mount_to_agent,
        audit_skill_id_fallback=request.skill_id,
        audit_source=request.source,
    )
    return await _install_response_with_adoption(
        flow.result,
        mount_result=flow.mount_result,
        pre_replace_batch_id=flow.pre_replace_batch_id,
        snapshot_truncated=flow.snapshot_truncated,
    )


@router.post("/update", response_model=SkillInstallResponse)
async def update_skill(
    request: SkillUpdateRequest,
) -> SkillInstallResponse:
    """Update a specific skill to its latest version.

    Uses the quarantine install flow: download -> scan -> replace.
    """
    require_local_skills_capability()
    from myrm_agent_harness.agent.skills.market.autoupdate import SkillUpdateInfo

    update_info = SkillUpdateInfo(
        skill_name=request.skill_name,
        current_version="",
        remote_version="",
        source=request.source,
        skill_id=request.skill_id,
        has_update=True,
    )
    checker = get_update_checker()
    result = await checker.update_skill(
        update_info,
        "default",
        allow_downgrade=request.allow_downgrade,
    )

    mount_result = None
    if result.success:
        _audit_skill_action("update", result.skill_id or request.skill_id, source=request.source)
        mount_result = await maybe_mount_after_install(
            result,
            agent_id=None,
            mount_to_agent=True,
        )

    return await _install_response_with_adoption(
        result,
        mount_result=mount_result,
        pre_replace_batch_id=checker.last_market_replace_batch_id,
        snapshot_truncated=checker.last_market_replace_snapshot_truncated,
    )


@router.post("/uninstall", response_model=SkillInstallResponse)
async def uninstall_skill(
    request: SkillUninstallRequest,
) -> SkillInstallResponse:
    """Uninstall a locally installed skill.

    When the skill is referenced by other in-library skills and force is
    False, the request is rejected with the impacted dependent list.
    """
    require_local_skills_capability()
    if not request.force:
        from app.core.skills.gates.dependency_guard import get_dependents_for_skill

        dependents = await get_dependents_for_skill(request.skill_id)
        if dependents:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "DEPENDENTS_EXIST",
                    "message": (
                        f"Skill is referenced by {len(dependents)} other skill(s). "
                        "Review them before uninstalling, or force-uninstall."
                    ),
                    "impacted_dependents": dependents,
                },
            )
    result = await market_service.uninstall(request.skill_id)
    if result.success:
        _audit_skill_action("uninstall", request.skill_id)
        try:
            from app.core.skills.config_version import bump_skill_config_version
            from app.core.skills.discovery.adopt import remove_skill_from_all_agents
            from app.core.skills.store.service import skills_service
            from app.services.event.app_event_bus import (
                AppEvent,
                AppEventType,
                get_event_bus,
            )

            await skills_service.user_config.disable_local_skill(request.skill_id)
            cleaned_agents_count = await remove_skill_from_all_agents(request.skill_id)
            if cleaned_agents_count > 0:
                logger.info(
                    "Cleaned uninstalled skill %s from %d agent(s)",
                    request.skill_id,
                    cleaned_agents_count,
                )
            bump_skill_config_version()
            get_event_bus().publish(
                AppEvent(
                    event_type=AppEventType.SKILL_POOL_UPDATED,
                    data={
                        "action": "uninstall",
                        "skill_id": request.skill_id,
                        "uninstalled_skills": list(result.installed_skills),
                        "cleaned_agents_count": cleaned_agents_count,
                    },
                )
            )
        except Exception as exc:
            logger.warning("Failed to broadcast SKILL_POOL_UPDATED on uninstall: %s", exc)
    return SkillInstallResponse(
        success=result.success,
        skill_name=result.skill_name,
        skill_id=result.skill_id,
        installed_path=result.installed_path,
        error=result.error,
        error_code=result.error_code,
    )


@router.post("/analyze-url", response_model=SkillAnalyzeUrlResponse)
async def analyze_skill_url(
    request: SkillInstallFromUrlRequest,
) -> SkillAnalyzeUrlResponse:
    """Analyze a GitHub URL to find specific skill paths."""
    raw_urls = await market_service.analyze_url(request.url)
    urls: list[SkillUrlInfo] = []
    for item in raw_urls:
        if not isinstance(item, dict):
            continue
        urls.append(
            SkillUrlInfo(
                url=str(item.get("url", "")),
                name=str(item.get("name", "")),
                description=str(item.get("description", "")),
                is_installed=bool(item.get("is_installed", False)),
            )
        )
    return SkillAnalyzeUrlResponse(urls=urls)


@router.post("/install-from-url", response_model=SkillInstallResponse)
async def install_skill_from_url(
    request: SkillInstallFromUrlRequest,
) -> SkillInstallResponse:
    """Install a skill directly from a GitHub URL."""
    require_local_skills_capability()
    from app.core.skills.discovery.market_install_flow import run_market_install_flow_from_url

    flow = await run_market_install_flow_from_url(
        request.url,
        allow_downgrade=request.allow_downgrade,
        agent_id=request.agent_id,
        mount_to_agent=request.mount_to_agent,
    )
    return await _install_response_with_adoption(
        flow.result,
        mount_result=flow.mount_result,
        pre_replace_batch_id=flow.pre_replace_batch_id,
        snapshot_truncated=flow.snapshot_truncated,
    )
