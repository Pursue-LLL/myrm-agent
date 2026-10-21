"""Skills discovery API domain: search, install, preview, update, uninstall, sources.

[INPUT]
- Discovery request payloads from the skills router (JSON body).
- Search/install orchestration from ``app.core.skills.marketplace`` and the harness market service.

[OUTPUT]
- Aggregate facade re-exporting every public name of the ``discovery`` subpackage:
  - discovery: ``router`` (APIRouter prefix `/discovery`) + search/install/preview/update/source handlers
  - discovery_schemas: request/response Pydantic models

[POS]
Server business layer (Skills API). The discovery endpoints and their schemas are always wired
together and mounted via ``api.skills.router``, so they stay co-located under one facade.
"""

from app.api.skills.discovery.discovery import router
from app.api.skills.discovery.discovery_schemas import (
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
