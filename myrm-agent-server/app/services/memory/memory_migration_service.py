"""
[POS] app/services/memory/memory_migration_service.py
[INPUT] pathlib.Path, threading.Lock, myrm_agent_harness.toolkits.memory.sovereign_migration, app/schemas/memory_migration.py
[OUTPUT] MemoryMigrationService, get_memory_migration_service

Business service mediating third-party competitor asset detection and ingestion.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from threading import Lock

from myrm_agent_harness.toolkits.memory.sovereign_migration import (
    CompetitorDetectResult,
    CompetitorImportResult,
    CompetitorIngestionAdapter,
    CompetitorType,
)

from app.schemas.memory_migration import (
    CompetitorDetectResponseDTO,
    CompetitorIngestRequestDTO,
    CompetitorIngestResponseDTO,
)

logger = logging.getLogger(__name__)


class MemoryMigrationService:
    """Service detecting and ingesting third-party competitor assets."""

    def __init__(
        self,
        competitor_adapter: CompetitorIngestionAdapter | None = None,
        default_storage_dir: Path | str | None = None,
    ) -> None:
        self._competitor_adapter = competitor_adapter or CompetitorIngestionAdapter()

        if default_storage_dir is not None:
            self._default_storage_dir = Path(default_storage_dir).resolve()
        else:
            base_dir_env = os.getenv("MYRM_MEMORY_STORAGE_DIR", ".myrm")
            self._default_storage_dir = Path(base_dir_env).resolve()
        logger.info("MemoryMigrationService initialized with storage_dir=%s", self._default_storage_dir)

    def detect_competitors(self) -> CompetitorDetectResponseDTO:
        """Probe local workstation environment for competitor folders or instructions."""
        detect_result: CompetitorDetectResult = self._competitor_adapter.detect()
        return CompetitorDetectResponseDTO(
            detected_competitors=[c.value for c in detect_result.detected_competitors],
            hermes_dir=detect_result.hermes_dir,
            claude_code_rule_path=detect_result.claude_code_rule_path,
            codex_rule_path=detect_result.codex_rule_path,
        )

    def ingest_competitor(self, request: CompetitorIngestRequestDTO) -> CompetitorIngestResponseDTO:
        """Import rules, memories, and skills from a competitor source."""
        type_map: dict[str, CompetitorType] = {
            "hermes": CompetitorType.HERMES,
            "claude_code": CompetitorType.CLAUDE_CODE,
            "codex": CompetitorType.CODEX,
        }
        competitor_type = type_map.get(request.competitor)
        if competitor_type is None:
            raise ValueError(f"Unsupported competitor type '{request.competitor}'. Supported: {list(type_map.keys())}")

        target_dir = (
            Path(request.target_destination_dir).resolve() if request.target_destination_dir else self._default_storage_dir
        )

        import_res: CompetitorImportResult = self._competitor_adapter.ingest(
            competitor=competitor_type,
            source_path=request.source_path,
            target_destination_dir=target_dir,
        )

        return CompetitorIngestResponseDTO(
            success=import_res.success,
            imported_rules_count=import_res.imported_rules_count,
            imported_skills_count=import_res.imported_skills_count,
            imported_memories_count=import_res.imported_memories_count,
            details=import_res.details,
        )


_service_lock = Lock()
_service_instance: MemoryMigrationService | None = None


def get_memory_migration_service() -> MemoryMigrationService:
    """Return thread-safe singleton instance of MemoryMigrationService."""
    global _service_instance
    with _service_lock:
        if _service_instance is None:
            _service_instance = MemoryMigrationService()
        return _service_instance
