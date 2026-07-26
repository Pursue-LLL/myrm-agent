"""Skill discovery API endpoints.

[INPUT]
app.api.skills.discovery_schemas (POS: Request/response Pydantic models)
app.api.skills.audit::_audit_skill_action (POS: Skill action audit logging)
app.core.skills.discovery_service::SkillDiscoveryService (POS: Skill search/install orchestrator)
app.core.skills.discovery_autoupdate::get_update_checker (POS: Update availability checker)

[OUTPUT]
router: FastAPI router with skill search, install, preview, update, uninstall,
        URL analysis, and custom source management endpoints.

[POS]
Skill discovery API. Delegates to harness BaseSkillDiscoveryService for
search/install/preview and to server-layer services for update checking
and custom source management.
"""

import logging
from typing import cast

from fastapi import APIRouter, HTTPException, Query
from myrm_agent_harness.agent.skills.discovery.service import BaseSkillDiscoveryService

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
from app.core.skills.discovery_autoupdate import get_update_checker
from app.core.skills.discovery_service import SkillDiscoveryService, discovery_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/discovery")


def _discovery_framework(svc: SkillDiscoveryService) -> BaseSkillDiscoveryService:
    return cast(BaseSkillDiscoveryService, svc._base)


@router.get("/search", response_model=SkillSearchResponse)
async def search_skills(
    q: str = Query("", description="Search keywords (empty returns popular skills)"),
    limit: int = Query(30, ge=1, le=50, description="Max results"),
) -> SkillSearchResponse:
    """Search skills from external sources.

    Searches across GitHub, skills.sh, and prebuilt skills.
    When q is empty, returns all available skills sorted by popularity.
    """
    enriched = await discovery_service.search(q, limit)
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
        preview = await _discovery_framework(discovery_service).preview(request.skill_id, request.source)
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
    )


@router.post("/install", response_model=SkillInstallResponse)
async def install_skill(
    request: SkillInstallRequest,
) -> SkillInstallResponse:
    """Install a skill from external source to local filesystem."""
    result = await discovery_service.install(request.skill_id, request.source)
    if result.success:
        _audit_skill_action("install", result.skill_id or request.skill_id, source=request.source)
    return SkillInstallResponse(
        success=result.success,
        skill_name=result.skill_name,
        skill_id=result.skill_id,
        installed_path=result.installed_path,
        error=result.error,
        error_code=result.error_code,
    )


@router.get("/detail/{source}/{skill_id:path}", response_model=SkillSearchResultResponse | None)
async def get_skill_detail(
    source: str,
    skill_id: str,
) -> SkillSearchResultResponse | None:
    """Get detailed information about a specific skill."""
    result = await _discovery_framework(discovery_service).get_detail(skill_id, source)
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
    from myrm_agent_harness.agent.skills.discovery.autoupdate import SkillUpdateInfo

    update_info = SkillUpdateInfo(
        skill_name=request.skill_name,
        current_version="",
        remote_version="",
        source=request.source,
        skill_id=request.skill_id,
        has_update=True,
    )
    checker = get_update_checker()
    result = await checker.update_skill(update_info, "default")

    if result.success:
        _audit_skill_action("update", result.skill_id or request.skill_id, source=request.source)

    return SkillInstallResponse(
        success=result.success,
        skill_name=result.skill_name,
        skill_id=result.skill_id,
        installed_path=result.installed_path,
        error=result.error,
        error_code=result.error_code,
    )


@router.post("/uninstall", response_model=SkillInstallResponse)
async def uninstall_skill(
    request: SkillUninstallRequest,
) -> SkillInstallResponse:
    """Uninstall a locally installed skill."""
    result = await discovery_service.uninstall(request.skill_id)
    if result.success:
        _audit_skill_action("uninstall", request.skill_id)
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
    raw_urls = await discovery_service.analyze_url(request.url)
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
    result = await discovery_service.install_from_url(request.url)
    if result.success:
        _audit_skill_action("install_from_url", result.skill_id or request.url, source="github")
    return SkillInstallResponse(
        success=result.success,
        skill_name=result.skill_name,
        skill_id=result.skill_id,
        installed_path=result.installed_path,
        error=result.error,
        error_code=result.error_code,
    )


# ---------------------------------------------------------------------------
# Custom Source Management
# ---------------------------------------------------------------------------


@router.get("/sources", response_model=CustomSourceListResponse)
async def list_custom_sources() -> CustomSourceListResponse:
    """List all user-configured custom skill sources."""
    from app.core.skills.custom_source_config import load_custom_sources

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
    from myrm_agent_harness.agent.skills.discovery.sources.wellknown import WellKnownSkillSource

    from app.core.skills.custom_source_config import add_custom_source as _add_source

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

    discovery_service._base.register_source(source)

    return CustomSourceProbeResponse(reachable=True, skill_count=skill_count, url=request.url)


@router.delete("/sources")
async def remove_custom_source_endpoint(
    url: str = Query(..., description="Source URL to remove"),
) -> dict[str, bool]:
    """Remove a custom skill source."""
    from urllib.parse import urlparse

    from app.core.skills.custom_source_config import remove_custom_source

    removed = remove_custom_source(url)
    if not removed:
        raise HTTPException(status_code=404, detail=f"Source not found: {url}")

    parsed = urlparse(url.rstrip("/"))
    source_name = f"well-known:{parsed.scheme}://{parsed.netloc}"
    discovery_service._base.unregister_source(source_name)

    return {"removed": True}
