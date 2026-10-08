"""Multi-platform memory migration wizard business service provider.

[POS]
Singleton service managing discovery of external competitor assets, triggering
safe deduplicated migration pipelines, and producing audit telemetry reports.

[INPUT]
- collections.abc.Sequence, pathlib.Path
- myrm_agent_harness.toolkits.memory (
    CompetitorAssetScanner,
    MigrationRunReport,
    MigrationSourceType,
    MultiPlatformMigrationEngine,
  )
- app.schemas.memory_migration_wizard (
    DetectedCandidateDTO,
    MigrationDetectRequestDTO,
    MigrationDetectResponseDTO,
    MigrationImportRequestDTO,
    MigrationImportResponseDTO,
    MigrationRunReportDTO,
    MigrationSourceTypeDTO,
    MigrationSourcesListResponseDTO,
  )

[OUTPUT]
- MigrationWizardService, get_migration_wizard_service
"""

from __future__ import annotations

from pathlib import Path

from myrm_agent_harness.toolkits.memory import (
    CompetitorAssetScanner,
    MigrationRunReport,
    MigrationSourceType,
    MultiPlatformMigrationEngine,
)

from app.schemas.memory_migration_wizard import (
    DetectedCandidateDTO,
    MigrationDetectRequestDTO,
    MigrationDetectResponseDTO,
    MigrationImportRequestDTO,
    MigrationImportResponseDTO,
    MigrationRunReportDTO,
    MigrationSourcesListResponseDTO,
)


class MigrationWizardService:
    """Service mediating multi-platform memory discovery, parsing, chunking, and ingestion."""

    def __init__(
        self,
        scanner: CompetitorAssetScanner | None = None,
        engine: MultiPlatformMigrationEngine | None = None,
    ) -> None:
        self._scanner = scanner or CompetitorAssetScanner()
        self._engine = engine or MultiPlatformMigrationEngine()

    def get_supported_sources(self) -> MigrationSourcesListResponseDTO:
        """Return the list of all supported external ecosystem format identifiers."""
        return MigrationSourcesListResponseDTO(
            supported_sources=[
                "openclaw",
                "hermes",
                "chatgpt_export",
                "claude_project",
                "markdown_tree",
                "generic_json",
            ]
        )

    def detect_assets(self, request: MigrationDetectRequestDTO) -> MigrationDetectResponseDTO:
        """Scan workspace and user directories to discover competitor artifacts."""
        artifacts = self._scanner.scan(custom_candidates=request.custom_candidates)
        candidates: list[DetectedCandidateDTO] = []

        for art in artifacts:
            source_val = str(art.source_kind.value).lower()
            candidates.append(
                DetectedCandidateDTO(
                    source_type=source_val,  # type: ignore[arg-type]
                    artifact_path=art.artifact_path,
                    estimated_entries=art.estimated_entries,
                    summary=art.summary,
                )
            )

        return MigrationDetectResponseDTO(
            total_detected=len(candidates),
            candidates=candidates,
        )

    async def import_memory(self, request: MigrationImportRequestDTO) -> MigrationImportResponseDTO:
        """Execute one-click migration for a file path or raw text payload."""
        source_type = MigrationSourceType(request.source_type)

        if request.file_path:
            _, report = await self._engine.migrate_file(
                source_type=source_type,
                file_path=Path(request.file_path),
            )
        elif request.raw_content is not None:
            _, report = await self._engine.migrate_payload(
                source_type=source_type,
                raw_content=request.raw_content,
                source_label=request.source_label,
            )
        else:
            raise ValueError("Either file_path or raw_content must be provided for migration")

        report_dto = self._to_report_dto(report)
        return MigrationImportResponseDTO(
            success=True,
            report=report_dto,
        )

    def _to_report_dto(self, report: MigrationRunReport) -> MigrationRunReportDTO:
        return MigrationRunReportDTO(
            migration_id=report.migration_id,
            source_type=report.source_type.value,  # type: ignore[arg-type]
            source_path=report.source_path,
            total_scanned=report.total_scanned,
            total_admitted=report.total_admitted,
            total_skipped_duplicates=report.total_skipped_duplicates,
            total_chunks_generated=report.total_chunks_generated,
            vector_ingestion_status=report.vector_ingestion_status,
            latency_ms=report.latency_ms,
            timestamp=report.timestamp,
        )


_wizard_service_instance: MigrationWizardService | None = None


def get_migration_wizard_service() -> MigrationWizardService:
    """FastAPI dependency provider for MigrationWizardService singleton."""
    global _wizard_service_instance
    if _wizard_service_instance is None:
        _wizard_service_instance = MigrationWizardService()
    return _wizard_service_instance
