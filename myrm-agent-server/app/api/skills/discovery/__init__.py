"""Skills discovery API domain: search, install, preview, update, uninstall, sources.

[INPUT]
- Discovery request payloads from the skills router (JSON body).
- Search/install orchestration from ``app.core.skills.marketplace`` and the harness market service.

[OUTPUT]
- Aggregate facade re-exporting every public name of the ``discovery`` subpackage:
  - routes / install: ``router`` (APIRouter prefix `/discovery`) + read and write handlers
  - schemas: request/response Pydantic models

[POS]
Server business layer (Skills API). The discovery endpoints and their schemas are always wired
together and mounted via ``api.skills.router``, so they stay co-located under one facade.
"""

from fastapi import APIRouter

from app.api.skills.discovery.index_admin import router as index_admin_router
from app.api.skills.discovery.install import router as install_router
from app.api.skills.discovery.routes import router as routes_router
from app.api.skills.discovery.schemas import (
    CustomSourceListResponse,
    CustomSourceProbeResponse,
    CustomSourceRequest,
    CustomSourceResponse,
    PrerequisiteDiagnosticResponse,
    ScanFindingResponse,
    SkillAnalyzeUrlResponse,
    SkillInstallFromUrlRequest,
    SkillInstallRequest,
    SkillInstallResponse,
    SkillPoolSyncRequest,
    SkillPoolSyncResponse,
    SkillPreviewRequest,
    SkillPreviewResponse,
    SkillReceiptResponse,
    SkillSearchResponse,
    SkillSearchResultResponse,
    SkillUninstallRequest,
    SkillUpdateInfoResponse,
    SkillUpdateRequest,
    SkillUrlInfo,
    StaticIndexStatusResponse,
    UpdateCheckResponse,
)
from app.api.skills.discovery.sources import router as sources_router

router = APIRouter(prefix="/discovery")
router.include_router(install_router)
router.include_router(routes_router)
router.include_router(sources_router)
router.include_router(index_admin_router)

__all__ = [
    "CustomSourceListResponse",
    "CustomSourceProbeResponse",
    "CustomSourceRequest",
    "CustomSourceResponse",
    "PrerequisiteDiagnosticResponse",
    "ScanFindingResponse",
    "SkillAnalyzeUrlResponse",
    "SkillInstallFromUrlRequest",
    "SkillInstallRequest",
    "SkillInstallResponse",
    "SkillPoolSyncRequest",
    "SkillPoolSyncResponse",
    "SkillPreviewRequest",
    "SkillPreviewResponse",
    "SkillReceiptResponse",
    "SkillSearchResponse",
    "SkillSearchResultResponse",
    "SkillUninstallRequest",
    "SkillUpdateInfoResponse",
    "SkillUpdateRequest",
    "SkillUrlInfo",
    "StaticIndexStatusResponse",
    "UpdateCheckResponse",
    "router",
]
