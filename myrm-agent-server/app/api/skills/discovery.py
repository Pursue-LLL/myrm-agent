"""Skill discovery API endpoints.

[INPUT]
app.api.skills.discovery_schemas (POS: Request/response Pydantic models)
app.api.skills.audit::_audit_skill_action (POS: Skill action audit logging)
app.core.skills.marketplace.market_service::SkillMarketService (POS: Skill search/install orchestrator)
app.core.skills.discovery.mount::maybe_mount_after_install (POS: Post-install user catalog enable)
app.core.skills.discovery.adopt::complete_discovery_adoption (POS: Explicit allowlist append after install)
app.core.skills.discovery.autoupdate::get_update_checker (POS: Update availability checker)

[OUTPUT]
router: FastAPI router with skill search, install, preview, update, uninstall,
        registry mirror probe, URL analysis, and custom source management endpoints.

[POS]
Skill discovery API. Delegates to harness BaseSkillMarketService for
search/install/preview and to server-layer services for update checking
and custom source management.
"""

import logging
from typing import cast

from fastapi import APIRouter, HTTPException, Query
from myrm_agent_harness.agent.skills.market.service import BaseSkillMarketService
from myrm_agent_harness.backends.skills.market_protocols import SkillInstallResult

from app.api.skills._deploy_capability import require_local_skills_capability
from app.api.skills.audit import _audit_skill_action
from app.api.skills.discovery_schemas import (
    CustomSourceListResponse,
    CustomSourceProbeResponse,
    CustomSourceRequest,
    CustomSourceResponse,
    ScanFindingResponse,
    SkillAnalyzeUrlResponse,
    SkillInstallFromUrlRequest,
    SkillInstallRequest,
    SkillInstallResponse,
    SkillPoolSyncRequest,
    SkillPoolSyncResponse,
    SkillPreviewRequest,
    SkillPreviewResponse,
    SkillSearchResponse,
    SkillSearchResultResponse,
    SkillUninstallRequest,
    SkillUpdateInfoResponse,
    SkillUpdateRequest,
    SkillUrlInfo,
    UpdateCheckResponse,
)
from app.core.skills.discovery.adopt import complete_discovery_adoption
from app.core.skills.discovery.autoupdate import get_update_checker
from app.core.skills.discovery.mount import (
    SkillMountResult,
    maybe_mount_after_install,
    resolve_mount_skill_id,
)
from app.core.skills.marketplace.market_service import (
    SkillMarketService,
    market_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/discovery")


def _discovery_framework(svc: SkillMarketService) -> BaseSkillMarketService:
    return cast(BaseSkillMarketService, svc._base)


def _install_response(
    result: SkillInstallResult,
    *,
    mount_result: SkillMountResult | None = None,
    allowlist_appended: bool = False,
    allowlist_append_error: str = "",
) -> SkillInstallResponse:
    from app.api.skills.discovery_schemas import SkillReceiptResponse

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
    )


async def _install_response_with_adoption(
    result: SkillInstallResult,
    *,
    mount_result: SkillMountResult | None = None,
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
    )


@router.get("/registry-probe")
async def probe_registry_mirror(
    mirror: str = Query("cn", description="Mirror preset to probe (cn|intl)"),
    url: str = Query("", description="Explicit registry base URL to probe"),
) -> dict[str, bool | str]:
    """Probe ClawHub-compatible registry reachability before switching mirrors."""
    from app.core.skills.marketplace.clawhub_probe import (
        probe_clawhub_registry,
        probe_configured_cn_mirror,
    )

    explicit = url.strip()
    if explicit:
        reachable, detail = await probe_clawhub_registry(explicit)
        return {"reachable": reachable, "error": detail}

    if mirror.strip().lower() == "cn":
        reachable, detail = await probe_configured_cn_mirror()
    else:
        from myrm_agent_harness.agent.skills.market.sources.clawhub_registry import (
            CLAWHUB_DEFAULT_URL,
        )

        reachable, detail = await probe_clawhub_registry(CLAWHUB_DEFAULT_URL)
    return {"reachable": reachable, "error": detail}


@router.get("/search", response_model=SkillSearchResponse)
async def search_skills(
    q: str = Query(
        "",
        description="Search keywords (empty returns no results; user must enter a query)",
    ),
    limit: int = Query(30, ge=1, le=50, description="Max results"),
    package_type: str = Query("all", description="Filter by package type: all | skill | agent_plugin"),
) -> SkillSearchResponse:
    """Search skills from external sources.

    Searches across configured discovery sources when q is non-empty.
    Empty q returns no results (browse requires an explicit search).
    """
    await market_service.ensure_clawhub_registry()
    enriched = await market_service.search(q, limit)
    if package_type and package_type != "all":
        enriched = [e for e in enriched if getattr(e.result, "package_type", "skill") == package_type]
    installed_ids = await market_service.get_installed_local_ids_by_name()
    return SkillSearchResponse(
        results=[
            SkillSearchResultResponse(
                id=e.result.id,
                name=e.result.name,
                description=e.result.description,
                source=e.result.source,
                author=e.result.author,
                install_url=e.result.install_url,
                install_method=e.result.install_method,
                version=e.result.version,
                stars=e.result.stars,
                downloads=e.result.downloads,
                tags=list(e.result.tags),
                readme_url=e.result.readme_url,
                subdirectory=e.result.subdirectory,
                installed_version=e.installed_version,
                upgrade_available=e.upgrade_available,
                installed_skill_id=installed_ids.get(e.result.name.lower(), ""),
                package_type=e.result.package_type,
                keywords=list(e.result.keywords),
                declared_mcp_servers=list(getattr(e.result, "declared_mcp_servers", [])),
            )
            for e in enriched
        ],
        total=len(enriched),
        query=q,
    )


@router.post("/preview", response_model=SkillPreviewResponse)
async def preview_skill(
    request: SkillPreviewRequest,
) -> SkillPreviewResponse:
    """Preview a skill before installation.

    Downloads the skill content and runs a security scan without installing.
    """
    try:
        preview = await _discovery_framework(market_service).preview(request.skill_id, request.source)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e

    return SkillPreviewResponse(
        skill_id=preview.skill_id,
        name=preview.name,
        description=preview.description,
        version=preview.version,
        files=preview.files,
        scan_findings=[
            ScanFindingResponse(
                threat_type=f.threat_type,
                severity=int(f.severity),
                description=f.description,
                line_number=f.line_number,
            )
            for f in preview.scan_findings
        ],
        is_clean=preview.is_clean,
        package_type=getattr(preview, "package_type", "skill"),
        installed_skills=list(getattr(preview, "installed_skills", [])),
        declared_mcp_servers=list(getattr(preview, "declared_mcp_servers", [])),
    )


@router.post("/install", response_model=SkillInstallResponse)
async def install_skill(
    request: SkillInstallRequest,
) -> SkillInstallResponse:
    """Install a skill from external source to local filesystem."""
    require_local_skills_capability()
    await market_service.ensure_clawhub_registry()
    result = await market_service.install(
        request.skill_id,
        request.source,
        allow_downgrade=request.allow_downgrade,
    )
    mount_result = None
    if result.success:
        _audit_skill_action("install", result.skill_id or request.skill_id, source=request.source)
        mount_result = await maybe_mount_after_install(
            result,
            agent_id=request.agent_id,
            mount_to_agent=request.mount_to_agent,
        )
    return await _install_response_with_adoption(result, mount_result=mount_result)


@router.get("/detail/{source}/{skill_id:path}", response_model=SkillSearchResultResponse | None)
async def get_skill_detail(
    source: str,
    skill_id: str,
) -> SkillSearchResultResponse | None:
    """Get detailed information about a specific skill."""
    result = await _discovery_framework(market_service).get_detail(skill_id, source)
    if not result:
        raise HTTPException(status_code=404, detail=f"Skill not found: {skill_id}")
    return SkillSearchResultResponse(
        id=result.id,
        name=result.name,
        description=result.description,
        source=result.source,
        author=result.author,
        install_url=result.install_url,
        install_method=result.install_method,
        version=result.version,
        stars=result.stars,
        downloads=result.downloads,
        tags=list(result.tags),
        readme_url=result.readme_url,
        subdirectory=result.subdirectory,
        package_type=result.package_type,
        keywords=list(result.keywords),
        declared_mcp_servers=list(getattr(result, "declared_mcp_servers", [])),
    )


@router.get("/updates", response_model=UpdateCheckResponse)
async def check_skill_updates(
    force: bool = Query(False, description="Bypass cooldown and re-check"),
) -> UpdateCheckResponse:
    """Check installed skills for available updates.

    Results are cached with a 10-minute cooldown. Use force=true to bypass.
    """
    checker = get_update_checker()
    result = await checker.check_updates(user_id="sandbox", force=force)
    return UpdateCheckResponse(
        has_updates=result.has_updates,
        updates=[
            SkillUpdateInfoResponse(
                skill_name=u.skill_name,
                current_version=u.current_version,
                remote_version=u.remote_version,
                source=u.source,
                skill_id=u.skill_id,
                has_update=u.has_update,
            )
            for u in result.available_updates
        ],
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

    return await _install_response_with_adoption(result, mount_result=mount_result)


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
    await market_service.ensure_clawhub_registry()
    result = await market_service.install_from_url(
        request.url,
        allow_downgrade=request.allow_downgrade,
    )
    mount_result = None
    if result.success:
        _audit_skill_action("install_from_url", result.skill_id or request.url, source="github")
        mount_result = await maybe_mount_after_install(
            result,
            agent_id=request.agent_id,
            mount_to_agent=request.mount_to_agent,
        )
    return await _install_response_with_adoption(result, mount_result=mount_result)


# ---------------------------------------------------------------------------
# Custom Source Management
# ---------------------------------------------------------------------------


@router.get("/sources", response_model=CustomSourceListResponse)
async def list_custom_sources() -> CustomSourceListResponse:
    """List all user-configured custom skill sources."""
    from app.core.skills.marketplace.custom_source_config import load_custom_sources

    config = load_custom_sources()
    return CustomSourceListResponse(
        sources=[
            CustomSourceResponse(
                url=s.url,
                source_type=s.source_type,
                label=s.label,
                healthy=s.healthy,
            )
            for s in config.sources
        ]
    )


@router.post("/sources", response_model=CustomSourceProbeResponse)
async def add_custom_source(
    request: CustomSourceRequest,
) -> CustomSourceProbeResponse:
    """Add a custom skill source after probing for reachability."""
    from myrm_agent_harness.agent.skills.market.sources.wellknown import (
        WellKnownSkillSource,
    )

    from app.core.skills.marketplace.custom_source_config import (
        add_custom_source as _add_source,
    )

    if request.source_type != "well-known":
        raise HTTPException(status_code=400, detail=f"Unsupported source type: {request.source_type}")

    source = WellKnownSkillSource(request.url)
    reachable, skill_count = await source.probe()

    if not reachable:
        raise HTTPException(status_code=422, detail=f"Cannot reach source: {request.url}")

    try:
        _add_source(request.url, request.source_type, request.label or request.url)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e

    market_service._base.register_source(source)

    return CustomSourceProbeResponse(reachable=True, skill_count=skill_count, url=request.url)


@router.delete("/sources")
async def remove_custom_source_endpoint(
    url: str = Query(..., description="Source URL to remove"),
) -> dict[str, bool]:
    """Remove a custom skill source."""
    from urllib.parse import urlparse

    from app.core.skills.marketplace.custom_source_config import remove_custom_source

    removed = remove_custom_source(url)
    if not removed:
        raise HTTPException(status_code=404, detail=f"Source not found: {url}")

    parsed = urlparse(url.rstrip("/"))
    source_name = f"well-known:{parsed.scheme}://{parsed.netloc}"
    market_service._base.unregister_source(source_name)

    return {"removed": True}


# ---------------------------------------------------------------------------
# Skill Pool Cross-Agent Sync
# ---------------------------------------------------------------------------


@router.post("/pool/sync", response_model=SkillPoolSyncResponse)
async def sync_skill_pool(
    request: SkillPoolSyncRequest,
) -> SkillPoolSyncResponse:
    """Sync a skill into multiple Agent profiles' explicit allowlists."""
    from app.core.skills.config_version import bump_skill_config_version
    from app.core.skills.discovery.adopt import sync_skill_to_agents
    from app.services.event.app_event_bus import (
        AppEvent,
        AppEventType,
        get_event_bus,
    )

    results = await sync_skill_to_agents(
        request.skill_id,
        request.target_agent_ids,
    )
    synced = [aid for aid, success in results.items() if success]
    failed = [aid for aid, success in results.items() if not success]

    if synced:
        bump_skill_config_version()
        try:
            get_event_bus().publish(
                AppEvent(
                    event_type=AppEventType.SKILL_POOL_UPDATED,
                    data={
                        "action": "sync",
                        "skill_id": request.skill_id,
                        "synced_agents": synced,
                    },
                )
            )
        except Exception as exc:
            logger.warning("Failed to broadcast SKILL_POOL_UPDATED on sync: %s", exc)

    return SkillPoolSyncResponse(
        success=bool(synced),
        skill_id=request.skill_id,
        synced_agents=synced,
        failed_agents=failed,
    )
