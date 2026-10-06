"""
[POS] app/api/memory/migration_router.py
[INPUT] fastapi, app/schemas/memory_migration.py, app/services/memory/memory_migration_service.py
[OUTPUT] router

FastAPI router exposing sovereign asset migration, portable packaging, restore, and competitor ingestion endpoints.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from app.schemas.memory_migration import (
    CompetitorDetectResponseDTO,
    CompetitorIngestRequestDTO,
    CompetitorIngestResponseDTO,
    ExportBundleRequestDTO,
    ExportBundleResponseDTO,
    RestoreBundleRequestDTO,
    RestoreBundleResponseDTO,
)
from app.services.memory.memory_migration_service import (
    MemoryMigrationService,
    get_memory_migration_service,
)

router = APIRouter()


@router.post(
    "/migration/export",
    response_model=ExportBundleResponseDTO,
    status_code=status.HTTP_200_OK,
    summary="Export all sovereign memory assets into verified .myrmpkg archive",
)
def export_sovereign_bundle(
    request: ExportBundleRequestDTO,
    service: MemoryMigrationService = Depends(get_memory_migration_service),
) -> ExportBundleResponseDTO:
    """Collect SQLite, wiki pages, and handoff records, relativize paths, and bundle into archive."""
    return service.export_bundle(request)


@router.post(
    "/migration/restore",
    response_model=RestoreBundleResponseDTO,
    status_code=status.HTTP_200_OK,
    summary="Restore sovereign asset bundle with checksum verification and dynamic path remapping",
)
def restore_sovereign_bundle(
    request: RestoreBundleRequestDTO,
    service: MemoryMigrationService = Depends(get_memory_migration_service),
) -> RestoreBundleResponseDTO:
    """Unpack .myrmpkg bundle, verify SHA-256 hashes, remap workspace paths, and restore assets."""
    return service.restore_bundle(request)


@router.get(
    "/migration/detect-competitors",
    response_model=CompetitorDetectResponseDTO,
    status_code=status.HTTP_200_OK,
    summary="Probe workstation for third-party competitor assets (Hermes, Claude Code, Codex)",
)
def detect_competitor_assets(
    service: MemoryMigrationService = Depends(get_memory_migration_service),
) -> CompetitorDetectResponseDTO:
    """Discover Hermes ~/.hermes, Claude Code CLAUDE.md, and Codex AGENTS.md on local machine."""
    return service.detect_competitors()


@router.post(
    "/migration/ingest-competitors",
    response_model=CompetitorIngestResponseDTO,
    status_code=status.HTTP_200_OK,
    summary="Ingest and translate third-party competitor rules, memories, and skills into Myrm",
)
def ingest_competitor_assets(
    request: CompetitorIngestRequestDTO,
    service: MemoryMigrationService = Depends(get_memory_migration_service),
) -> CompetitorIngestResponseDTO:
    """Translate Hermes memories/skills or Claude Code/Codex rules losslessly into Myrm."""
    return service.ingest_competitor(request)
