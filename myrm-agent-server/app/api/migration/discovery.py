"""Migration discovery API routes.

[INPUT]
HTTP GET request to scan for competitor data installations.

[OUTPUT]
JSON response with discovered competitor sources and confidence levels.

[POS]
Local/Tauri-only endpoint for competitor data auto-discovery. Returns detected
competitor AI assistant data directories with confidence scores and file metadata.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.config.deploy_mode import is_local_mode
from app.services.migration.competitor_discovery import (
    CompetitorSource,
    discover_competitors,
)
from app.services.migration.competitor_secrets_importer import import_competitor_secrets

router = APIRouter(prefix="/migration", tags=["migration"])


class DiscoveredFileResponse(BaseModel):
    path: str
    kind: str
    size_bytes: int = 0


class CompetitorSourceResponse(BaseModel):
    competitor: str
    root: str
    confidence: str
    files: list[DiscoveredFileResponse] = Field(default_factory=list)
    memory_count_estimate: int = 0
    skill_count: int = 0
    has_api_keys: bool = False


class DiscoveryResponse(BaseModel):
    sources: list[CompetitorSourceResponse] = Field(default_factory=list)
    scan_path: str = ""
    available: bool = True


def _to_response(source: CompetitorSource) -> CompetitorSourceResponse:
    return CompetitorSourceResponse(
        competitor=source.competitor,
        root=source.root,
        confidence=source.confidence,
        files=[
            DiscoveredFileResponse(path=f.path, kind=f.kind, size_bytes=f.size_bytes)
            for f in source.files
        ],
        memory_count_estimate=source.memory_count_estimate,
        skill_count=source.skill_count,
        has_api_keys=source.has_api_keys,
    )


class SecretsImportRequest(BaseModel):
    root: str = Field(..., min_length=1, description="Competitor data root directory")
    competitor: str = Field(..., min_length=1, description="Competitor identifier")


class SecretsImportResponse(BaseModel):
    imported_keys: list[str]
    skipped_keys: list[str]
    message: str


@router.post("/secrets/import", response_model=SecretsImportResponse)
async def import_competitor_secrets_endpoint(body: SecretsImportRequest) -> SecretsImportResponse:
    """Opt-in import of competitor .env API keys into provider config (local/Tauri only)."""

    if not is_local_mode():
        raise HTTPException(status_code=403, detail="Secret import is only available in local or Tauri mode")

    try:
        result = await import_competitor_secrets(Path(body.root))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return SecretsImportResponse(
        imported_keys=[str(k) for k in result.get("imported_keys", []) if isinstance(k, str)],
        skipped_keys=[str(k) for k in result.get("skipped_keys", []) if isinstance(k, str)],
        message=str(result.get("message", "")),
    )


@router.get("/discover", response_model=DiscoveryResponse)
async def discover_competitor_data() -> DiscoveryResponse:
    """Scan local filesystem for competitor AI assistant data.

    Only available in local/Tauri deployment modes. Returns empty in SaaS mode.
    """

    if not is_local_mode():
        return DiscoveryResponse(sources=[], available=False)

    result = discover_competitors()
    return DiscoveryResponse(
        sources=[_to_response(s) for s in result.sources],
        scan_path=result.scan_path,
        available=True,
    )
