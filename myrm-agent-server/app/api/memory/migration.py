"""[POS]: app/api/memory/migration.py
[INPUT]: FastAPI HTTP requests for competitor memory asset detection and ingestion.
[OUTPUT]: Strongly-typed JSON responses conforming to competitor memory migration API contracts.
"""

from fastapi import APIRouter, Depends, HTTPException
from myrm_agent_harness.toolkits.memory import (
    CompetitorMigrationService,
    CompetitorSourceKind,
    MigrationExecutionReport,
    NormalizedMemoryPayload,
)

from app.schemas.migration import (
    DetectArtifactsResponse,
    DetectedArtifactDTO,
    ImportArtifactRequest,
    ImportRawTextRequest,
    MigrationHistoryResponse,
    MigrationReportResponse,
    NormalizedMemoryDTO,
)
from app.services.memory.migration import get_competitor_migration_service

router = APIRouter(prefix="/migration", tags=["memory-migration"])


def _to_memory_dto(m: NormalizedMemoryPayload) -> NormalizedMemoryDTO:
    return NormalizedMemoryDTO(
        source_kind=m.source_kind.value,
        source_id=m.source_id,
        raw_content=m.raw_content,
        normalized_content=m.normalized_content,
        layer_recommendation=m.layer_recommendation,
        tags=m.tags,
        content_hash=m.content_hash,
        provenance_meta=m.provenance_meta,
    )


def _to_report_dto(rep: MigrationExecutionReport) -> MigrationReportResponse:
    return MigrationReportResponse(
        migration_id=rep.migration_id,
        source_kind=rep.source_kind.value,
        source_path=rep.source_path,
        total_scanned=rep.total_scanned,
        total_imported=rep.total_imported,
        total_skipped_duplicates=rep.total_skipped_duplicates,
        imported_entries=[_to_memory_dto(e) for e in rep.imported_entries],
        timestamp=rep.timestamp,
    )


@router.get("/detect-artifacts", response_model=DetectArtifactsResponse)
def detect_competitor_artifacts(
    custom_paths: str | None = None,
    service: CompetitorMigrationService = Depends(get_competitor_migration_service),
) -> DetectArtifactsResponse:
    """Scan local host filesystem to discover candidate competitor memory files."""
    paths_list = [p.strip() for p in custom_paths.split(",") if p.strip()] if custom_paths else None
    artifacts = service.scan_local_artifacts(custom_candidates=paths_list)
    dtos = [
        DetectedArtifactDTO(
            source_kind=a.source_kind.value,
            artifact_path=a.artifact_path,
            estimated_entries=a.estimated_entries,
            detected_timestamp=a.detected_timestamp,
            summary=a.summary,
        )
        for a in artifacts
    ]
    return DetectArtifactsResponse(total_detected=len(dtos), artifacts=dtos)


@router.post("/import-file", response_model=MigrationReportResponse)
def import_from_file(
    request: ImportArtifactRequest,
    service: CompetitorMigrationService = Depends(get_competitor_migration_service),
) -> MigrationReportResponse:
    """Translate and ingest memories from an external competitor file path."""
    try:
        source_kind = CompetitorSourceKind(request.source_kind)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid source_kind: {request.source_kind}. Must be one of {[k.value for k in CompetitorSourceKind]}",
        ) from None

    report = service.import_from_artifact(
        source_kind=source_kind, file_path=request.artifact_path
    )
    return _to_report_dto(report)


@router.post("/import-text", response_model=MigrationReportResponse)
def import_from_text(
    request: ImportRawTextRequest,
    service: CompetitorMigrationService = Depends(get_competitor_migration_service),
) -> MigrationReportResponse:
    """Translate and ingest memories directly from a raw serialized text payload."""
    try:
        source_kind = CompetitorSourceKind(request.source_kind)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid source_kind: {request.source_kind}. Must be one of {[k.value for k in CompetitorSourceKind]}",
        ) from None

    report = service.import_raw_text(
        source_kind=source_kind,
        raw_text=request.raw_text,
        source_label=request.source_label,
    )
    return _to_report_dto(report)


@router.get("/history", response_model=MigrationHistoryResponse)
def get_migration_history(
    service: CompetitorMigrationService = Depends(get_competitor_migration_service),
) -> MigrationHistoryResponse:
    """Retrieve audit trail of historical memory migration runs."""
    reports = service.list_migration_history()
    return MigrationHistoryResponse(
        total_records=len(reports),
        history=[_to_report_dto(r) for r in reports],
    )
