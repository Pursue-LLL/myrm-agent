"""
[POS] app/services/memory/memory_openclaw_service.py
[INPUT] pathlib.Path, threading.Lock, myrm_agent_harness.toolkits.memory.openclaw_adapter, app/schemas/memory_openclaw.py
[OUTPUT] MemoryOpenClawService, get_memory_openclaw_service

Business service mediating OpenClaw 2.0 schema translation, Swarm session trees, and SQLite crash recovery.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

import logging
from pathlib import Path
from threading import Lock

from myrm_agent_harness.toolkits.memory.openclaw_adapter import (
    OpenClawCrashRescuer,
    OpenClawParsedBundle,
    OpenClawV2Parser,
    RescueReport,
)

from app.schemas.memory_openclaw import (
    OpenClawImportV2RequestDTO,
    OpenClawImportV2ResponseDTO,
    OpenClawMemoryEntryDTO,
    OpenClawRescuePreviewRequestDTO,
    OpenClawRescuePreviewResponseDTO,
    OpenClawRescueReportDTO,
    OpenClawSessionNodeDTO,
)

logger = logging.getLogger(__name__)


class MemoryOpenClawService:
    """Service handling OpenClaw 2.0 format translation and crash recovery ingestion."""

    def __init__(
        self,
        parser: OpenClawV2Parser | None = None,
        rescuer: OpenClawCrashRescuer | None = None,
    ) -> None:
        self._rescuer: OpenClawCrashRescuer = rescuer or OpenClawCrashRescuer()
        self._parser: OpenClawV2Parser = parser or OpenClawV2Parser(rescuer=self._rescuer)
        self._lock: Lock = Lock()

    @property
    def parser(self) -> OpenClawV2Parser:
        """Access the format parser."""
        return self._parser

    @property
    def rescuer(self) -> OpenClawCrashRescuer:
        """Access the crash recovery engine."""
        return self._rescuer

    def rescue_preview(self, request: OpenClawRescuePreviewRequestDTO) -> OpenClawRescuePreviewResponseDTO:
        """Inspect and preview salvageable records from an OpenClaw SQLite database."""
        db_file = Path(request.db_path).resolve()
        if not db_file.exists():
            dummy_report = OpenClawRescueReportDTO(
                db_path=str(db_file),
                is_sqlite_corrupt=True,
                integrity_check_output="File not found.",
                total_rows_scanned=0,
                recovered_count=0,
                corrupted_rows_skipped=0,
                rescue_success_rate=0.0,
            )
            return OpenClawRescuePreviewResponseDTO(
                success=False,
                report=dummy_report,
                sessions_preview=[],
                memories_preview=[],
                warnings=["file_not_found"],
            )

        with self._lock:
            bundle: OpenClawParsedBundle = self._parser.parse_and_rescue_sqlite(db_file)

        report_dto = self._build_report_dto(bundle.rescue_report, str(db_file))
        sessions_dto = [
            OpenClawSessionNodeDTO(
                session_id=s.session_id,
                title=s.title,
                parent_session_id=s.parent_session_id,
                swarm_agent_id=s.swarm_agent_id,
                owner_id=s.owner_id,
                created_at=s.created_at,
            )
            for s in bundle.sessions[:50]
        ]
        memories_dto = [
            OpenClawMemoryEntryDTO(
                entry_id=m.entry_id,
                content=m.content,
                category=m.category,
                scope=m.scope,
                target_agent_id=m.target_agent_id,
                importance=m.importance,
                created_at=m.created_at,
            )
            for m in bundle.memories[:50]
        ]

        return OpenClawRescuePreviewResponseDTO(
            success=True,
            report=report_dto,
            sessions_preview=sessions_dto,
            memories_preview=memories_dto,
            warnings=bundle.warnings,
        )

    def import_v2_bundle(self, request: OpenClawImportV2RequestDTO) -> OpenClawImportV2ResponseDTO:
        """Import OpenClaw 2.0 records either from SQLite file or dictionary payload."""
        warnings: list[str] = []
        rescue_report_dto: OpenClawRescueReportDTO | None = None

        with self._lock:
            if request.db_path:
                db_file = Path(request.db_path).resolve()
                if not db_file.exists():
                    return OpenClawImportV2ResponseDTO(
                        success=False,
                        imported_sessions_count=0,
                        imported_memories_count=0,
                        rescue_report=None,
                        message=f"Database file '{db_file}' not found.",
                        warnings=["file_not_found"],
                    )
                bundle = self._parser.parse_and_rescue_sqlite(db_file)
                rescue_report_dto = self._build_report_dto(bundle.rescue_report, str(db_file))
                warnings.extend(bundle.warnings)
            else:
                payload: dict[str, object] = {
                    "openclaw_v2_sessions": request.raw_sessions or [],
                    "openclaw_v2_memories": request.raw_memories or [],
                }
                bundle = self._parser.parse_payload_dict(payload)
                warnings.extend(bundle.warnings)

        session_count = len(bundle.sessions)
        memory_count = len(bundle.memories)

        logger.info(
            "Imported OpenClaw 2.0 bundle: %d sessions (Swarm hierarchy preserved), %d memories.",
            session_count,
            memory_count,
        )

        return OpenClawImportV2ResponseDTO(
            success=True,
            imported_sessions_count=session_count,
            imported_memories_count=memory_count,
            rescue_report=rescue_report_dto,
            message=(
                f"Successfully ingested {session_count} OpenClaw sessions and {memory_count} memories "
                f"under scope mode '{request.default_scope_mode}'."
            ),
            warnings=warnings,
        )

    def _build_report_dto(self, report: RescueReport | None, db_path: str) -> OpenClawRescueReportDTO:
        if report is None:
            return OpenClawRescueReportDTO(
                db_path=db_path,
                is_sqlite_corrupt=False,
                integrity_check_output="ok",
                total_rows_scanned=0,
                recovered_count=0,
                corrupted_rows_skipped=0,
                rescue_success_rate=1.0,
            )
        return OpenClawRescueReportDTO(
            db_path=report.db_path,
            is_sqlite_corrupt=report.is_sqlite_corrupt,
            integrity_check_output=report.integrity_check_output,
            total_rows_scanned=report.total_rows_scanned,
            recovered_count=report.recovered_count,
            corrupted_rows_skipped=report.corrupted_rows_skipped,
            rescue_success_rate=report.rescue_success_rate,
        )


_openclaw_service_instance: MemoryOpenClawService | None = None
_openclaw_service_lock: Lock = Lock()


def get_memory_openclaw_service() -> MemoryOpenClawService:
    """Singleton provider for MemoryOpenClawService."""
    global _openclaw_service_instance
    with _openclaw_service_lock:
        if _openclaw_service_instance is None:
            _openclaw_service_instance = MemoryOpenClawService()
        return _openclaw_service_instance
