"""Multi-platform memory migration wizard API router.

[POS]
FastAPI endpoints for discovering external competitor memory assets,
executing safe deduplicated import pipelines, and retrieving migration audit telemetry.

[INPUT]
- fastapi (APIRouter, Depends, status, HTTPException)
- app.schemas.memory_migration_wizard (
    MigrationDetectRequestDTO,
    MigrationDetectResponseDTO,
    MigrationImportRequestDTO,
    MigrationImportResponseDTO,
    MigrationSourcesListResponseDTO,
  )
- app.services.memory.migration_wizard (
    MigrationWizardService,
    get_migration_wizard_service,
  )

[OUTPUT]
- router: APIRouter with /sources, /detect, and /import endpoints
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.schemas.memory_migration_wizard import (
    MigrationDetectRequestDTO,
    MigrationDetectResponseDTO,
    MigrationImportRequestDTO,
    MigrationImportResponseDTO,
    MigrationSourcesListResponseDTO,
)
from app.services.memory.migration_wizard import (
    MigrationWizardService,
    get_migration_wizard_service,
)

router = APIRouter(prefix="/migration-wizard", tags=["Memory Migration Wizard"])


@router.get(
    "/sources",
    response_model=MigrationSourcesListResponseDTO,
    summary="List all supported competitor platforms and memory formats",
    status_code=status.HTTP_200_OK,
)
async def list_supported_sources(
    service: MigrationWizardService = Depends(get_migration_wizard_service),
) -> MigrationSourcesListResponseDTO:
    """Return available ecosystem parsers (openclaw, hermes, chatgpt_export, etc.)."""
    return service.get_supported_sources()


@router.post(
    "/detect",
    response_model=MigrationDetectResponseDTO,
    summary="Scan local environment to discover existing competitor memory files",
    status_code=status.HTTP_200_OK,
)
async def detect_competitor_assets(
    payload: MigrationDetectRequestDTO,
    service: MigrationWizardService = Depends(get_migration_wizard_service),
) -> MigrationDetectResponseDTO:
    """Scan predefined workspace paths or custom directories for competitor artifacts."""
    return service.detect_assets(payload)


@router.post(
    "/import",
    response_model=MigrationImportResponseDTO,
    summary="One-click parse, deduplicate, sliding-window chunk, and ingest memory",
    status_code=status.HTTP_200_OK,
)
async def import_memory_asset(
    payload: MigrationImportRequestDTO,
    service: MigrationWizardService = Depends(get_migration_wizard_service),
) -> MigrationImportResponseDTO:
    """Execute safe multi-platform memory migration with 400/80 sliding-window chunking."""
    try:
        return await service.import_memory(payload)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Migration failed: {e}",
        ) from e
