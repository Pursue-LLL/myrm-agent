"""Migration discovery API routes.

[INPUT]
HTTP GET request to scan for competitor data installations.

[OUTPUT]
JSON discovery response; opt-in POST `/secrets/import` for competitor .env keys.

[POS]
Local/Tauri-only migration API (Hermes, OpenClaw, Claude Code, Codex discover;
secrets import opt-in). SaaS returns empty discovery.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.config.deploy_mode import is_local_mode
from app.services.migration.source.source_discovery import (
    ExternalSource,
    discover_external_sources,
)
from app.services.migration.source.source_manifest import (
    MigrationImportSource,
    migration_source_manifest_authoritative,
    migration_source_manifest_authoritative_for_ids,
    migration_source_manifest_payload,
)
from app.services.migration.source.source_secrets_importer import import_external_source_secrets

router = APIRouter(prefix="/migration", tags=["migration"])
logger = logging.getLogger(__name__)


class DiscoveredFileResponse(BaseModel):
    path: str
    kind: str
    size_bytes: int = 0


class ExternalSourceResponse(BaseModel):
    competitor: str
    root: str
    confidence: str
    files: list[DiscoveredFileResponse] = Field(default_factory=list)
    memory_count_estimate: int = 0
    skill_count: int = 0
    has_api_keys: bool = False


class MigrationSourceManifestItemResponse(BaseModel):
    id: str
    display_name: str
    import_source: MigrationImportSource
    discover_modes: list[Literal["local_scan", "zip_upload"]] = Field(default_factory=list)
    deep_link_enabled: bool = True


class DiscoveryResponse(BaseModel):
    sources: list[ExternalSourceResponse] = Field(default_factory=list)
    scan_path: str = ""
    available: bool = True
    source_manifest: list[MigrationSourceManifestItemResponse] = Field(default_factory=list)
    source_manifest_authoritative: bool = True


def _to_response(source: ExternalSource) -> ExternalSourceResponse:
    return ExternalSourceResponse(
        competitor=source.competitor,
        root=source.root,
        confidence=source.confidence,
        files=[DiscoveredFileResponse(path=f.path, kind=f.kind, size_bytes=f.size_bytes) for f in source.files],
        memory_count_estimate=source.memory_count_estimate,
        skill_count=source.skill_count,
        has_api_keys=source.has_api_keys,
    )


def build_source_manifest_response() -> list[MigrationSourceManifestItemResponse]:
    """Build the Wizard source manifest payload for frontend consumption."""

    return [MigrationSourceManifestItemResponse.model_validate(item) for item in migration_source_manifest_payload()]


def resolve_source_manifest_authoritative(manifest: list[MigrationSourceManifestItemResponse]) -> bool:
    """Resolve authoritative flag with SSOT completeness guard."""

    authoritative = migration_source_manifest_authoritative_for_ids(item.id for item in manifest)
    if authoritative:
        return True
    if migration_source_manifest_authoritative():
        logger.warning(
            "Migration source manifest incomplete in /migration/discover; authoritative flag downgraded",
        )
    return False


class SecretsImportRequest(BaseModel):
    root: str = Field(..., min_length=1, description="External data root directory")
    competitor: str = Field(..., min_length=1, description="Source identifier")


class SecretsImportResponse(BaseModel):
    imported_keys: list[str]
    skipped_keys: list[str]
    message: str


@router.post("/secrets/import", response_model=SecretsImportResponse)
async def import_external_source_secrets_endpoint(body: SecretsImportRequest) -> SecretsImportResponse:
    """Opt-in import of competitor .env API keys into provider config (local/Tauri only)."""

    if not is_local_mode():
        raise HTTPException(status_code=403, detail="Secret import is only available in local or Tauri mode")

    try:
        result = await import_external_source_secrets(Path(body.root))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return SecretsImportResponse(
        imported_keys=[str(k) for k in result.get("imported_keys", []) if isinstance(k, str)],
        skipped_keys=[str(k) for k in result.get("skipped_keys", []) if isinstance(k, str)],
        message=str(result.get("message", "")),
    )


@router.get("/discover", response_model=DiscoveryResponse)
async def discover_external_source_data() -> DiscoveryResponse:
    """Scan local filesystem for competitor AI assistant data.

    Only available in local/Tauri deployment modes. Returns empty in SaaS mode.
    """

    manifest = build_source_manifest_response()
    manifest_authoritative = resolve_source_manifest_authoritative(manifest)
    if not is_local_mode():
        return DiscoveryResponse(
            sources=[],
            available=False,
            source_manifest=manifest,
            source_manifest_authoritative=manifest_authoritative,
        )

    result = discover_external_sources()
    return DiscoveryResponse(
        sources=[_to_response(s) for s in result.sources],
        scan_path=result.scan_path,
        available=True,
        source_manifest=manifest,
        source_manifest_authoritative=manifest_authoritative,
    )
