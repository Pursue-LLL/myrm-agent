"""Skill discovery read/search endpoints.

[INPUT]
app.api.skills.discovery.install (POS: Install, update, uninstall and URL install routes)
app.api.skills.discovery.schemas (POS: Request/response Pydantic models)
app.core.skills.discovery.autoupdate::get_update_checker (POS: Update availability checker)
app.core.skills.marketplace.market_service::SkillMarketService (POS: Skill search/install orchestrator)

[OUTPUT]
router: FastAPI router with skill search, preview, detail, update check, registry mirror probe,
        custom source management, static index status and pool sync endpoints.

[POS]
Skill discovery API. Delegates search/preview to the harness market service, and leaves every
write path (install, update, uninstall) to discovery_install.
"""

import logging
from typing import cast

from fastapi import APIRouter, HTTPException, Query
from myrm_agent_harness.agent.skills.market.service import BaseSkillMarketService

from app.api.skills.discovery.install import router as install_router
from app.api.skills.discovery.schemas import (
    CustomSourceListResponse,
    CustomSourceProbeResponse,
    CustomSourceRequest,
    CustomSourceResponse,
    ScanFindingResponse,
    SkillPoolSyncRequest,
    SkillPoolSyncResponse,
    SkillPreviewRequest,
    SkillPreviewResponse,
    SkillSearchResponse,
    SkillSearchResultResponse,
    SkillUpdateInfoResponse,
    StaticIndexStatusResponse,
    UpdateCheckResponse,
)
from app.core.skills.discovery.autoupdate import get_update_checker
from app.core.skills.marketplace.market_service import (
    SkillMarketService,
    market_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/discovery")
router.include_router(install_router)


def _discovery_framework(svc: SkillMarketService) -> BaseSkillMarketService:
    return cast(BaseSkillMarketService, svc._base)


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
    from app.core.skills.marketplace.custom_source_config import (
        add_custom_source as _add_source,
    )

    if request.source_type == "well-known":
        from myrm_agent_harness.agent.skills.market.sources.wellknown import (
            WellKnownSkillSource,
        )

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

    elif request.source_type in ("github-tap", "tap"):
        from myrm_agent_harness.agent.skills.market.taps import (
            TapDirectoryScanner,
            TapSubscription,
        )

        tap_sub = TapSubscription(repo=request.url, label=request.label or request.url)
        scanner = TapDirectoryScanner(tap_sub)
        skills = await scanner.scan_skills(force_refresh=True)

        try:
            _add_source(request.url, "github-tap", request.label or request.url)
        except ValueError as e:
            raise HTTPException(status_code=409, detail=str(e)) from e

        return CustomSourceProbeResponse(reachable=True, skill_count=len(skills), url=request.url)

    else:
        raise HTTPException(status_code=400, detail=f"Unsupported source type: {request.source_type}")


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
    if parsed.scheme and parsed.netloc:
        source_name = f"well-known:{parsed.scheme}://{parsed.netloc}"
    else:
        source_name = f"github-tap:{url.strip('/')}"
    market_service._base.unregister_source(source_name)

    return {"removed": True}


@router.get("/static-index/status", response_model=StaticIndexStatusResponse)
async def get_static_index_status() -> StaticIndexStatusResponse:
    """Get the status and metadata of the centralized static skills index."""
    from myrm_agent_harness.agent.skills.market.sources.static_index import (
        StaticIndexSkillSource,
    )

    static_source = None
    for src in market_service._base._sources:
        if isinstance(src, StaticIndexSkillSource):
            static_source = src
            break

    if static_source is None:
        return StaticIndexStatusResponse(
            is_loaded=False,
            total_indexed_skills=0,
            source_name="static_index",
            source_url="",
            last_synced_at=0.0,
        )

    return StaticIndexStatusResponse(
        is_loaded=static_source._is_loaded,
        total_indexed_skills=static_source.total_indexed_skills,
        source_name=static_source.source_name,
        source_url=static_source._index_url,
        last_synced_at=static_source._last_synced_at,
    )


@router.post("/static-index/refresh", response_model=StaticIndexStatusResponse)
async def refresh_static_index() -> StaticIndexStatusResponse:
    """Trigger manual refresh of the centralized static skills index from CDN/mirror."""
    from myrm_agent_harness.agent.skills.market.sources.static_index import (
        StaticIndexSkillSource,
    )

    static_source = None
    for src in market_service._base._sources:
        if isinstance(src, StaticIndexSkillSource):
            static_source = src
            break

    if static_source is None:
        raise HTTPException(status_code=404, detail="Static index source is not registered")

    await static_source.force_refresh()

    return StaticIndexStatusResponse(
        is_loaded=static_source._is_loaded,
        total_indexed_skills=static_source.total_indexed_skills,
        source_name=static_source.source_name,
        source_url=static_source._index_url,
        last_synced_at=static_source._last_synced_at,
    )


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
