"""Skill discovery API endpoints

Search and install skills from external sources.
"""

import logging
from typing import cast

from fastapi import APIRouter, HTTPException, Query
from myrm_agent_harness.agent.skills.discovery.service import BaseSkillDiscoveryService
from pydantic import BaseModel

from app.api.skills.audit import _audit_skill_action
from app.core.skills.discovery_autoupdate import get_update_checker
from app.core.skills.discovery_service import SkillDiscoveryService, discovery_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/discovery")


def _discovery_framework(svc: SkillDiscoveryService) -> BaseSkillDiscoveryService:
    return cast(BaseSkillDiscoveryService, svc._base)


class SkillSearchResultResponse(BaseModel):
    """搜索结果"""

    id: str
    name: str
    description: str
    source: str
    author: str
    install_url: str
    install_method: str
    version: str = ""
    stars: int = 0
    downloads: int = 0
    tags: list[str] = []
    readme_url: str | None = None
    subdirectory: str | None = None
    installed_version: str = ""
    upgrade_available: bool = False


class SkillSearchResponse(BaseModel):
    """搜索响应"""

    results: list[SkillSearchResultResponse]
    total: int
    query: str


class SkillInstallRequest(BaseModel):
    """安装请求"""

    skill_id: str
    source: str


class SkillInstallResponse(BaseModel):
    """安装响应"""

    success: bool
    skill_name: str = ""
    skill_id: str = ""
    installed_path: str = ""
    error: str = ""


class SkillUpdateInfoResponse(BaseModel):
    """Update availability for one installed skill."""

    skill_name: str
    current_version: str
    remote_version: str
    source: str
    skill_id: str
    has_update: bool


class UpdateCheckResponse(BaseModel):
    """Batch update check response."""

    has_updates: bool
    updates: list[SkillUpdateInfoResponse]


class SkillUpdateRequest(BaseModel):
    """Request to update a specific skill."""

    skill_name: str
    skill_id: str
    source: str


class SkillUninstallRequest(BaseModel):
    """卸载请求"""

    skill_id: str


class SkillPreviewRequest(BaseModel):
    """预览请求"""

    skill_id: str
    source: str


class ScanFindingResponse(BaseModel):
    """安全扫描发现"""

    threat_type: str
    severity: int
    description: str
    line_number: int | None = None


class SkillPreviewResponse(BaseModel):
    """预览响应（含安全扫描结果）"""

    skill_id: str
    name: str
    description: str
    version: str
    files: list[str]
    scan_findings: list[ScanFindingResponse] = []
    is_clean: bool = True


@router.get("/search", response_model=SkillSearchResponse)
async def search_skills(
    q: str = Query("", description="Search keywords (empty returns popular skills)"),
    limit: int = Query(30, ge=1, le=50, description="Max results"),
) -> SkillSearchResponse:
    """Search skills from external sources

    Searches across GitHub, skills.sh, and prebuilt skills.
    When q is empty, returns all available skills sorted by popularity.
    When user_id is provided, marks results with upgrade availability.
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
    """Preview a skill before installation

    Downloads the skill content and runs a security scan without installing.
    Use this to show scan results to the user before confirming installation.
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
    )


@router.get("/detail/{source}/{skill_id:path}", response_model=SkillSearchResultResponse | None)
async def get_skill_detail(
    source: str,
    skill_id: str,
) -> SkillSearchResultResponse | None:
    """Get detailed information about a specific skill"""
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

    Uses the quarantine install flow: download → scan → replace.
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
    )


class SkillInstallFromUrlRequest(BaseModel):
    """URL 安装请求"""

    url: str


class SkillUrlInfo(BaseModel):
    """解析出的 GitHub 技能信息"""

    url: str
    name: str
    description: str = ""
    is_installed: bool


class SkillAnalyzeUrlResponse(BaseModel):
    """URL 分析结果"""

    urls: list[SkillUrlInfo]


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
    )
