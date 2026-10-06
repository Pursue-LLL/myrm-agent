"""
[POS] app/services/memory/memory_migration_service.py
[INPUT] pathlib.Path, time, threading.Lock, myrm_agent_harness.toolkits.memory.sovereign_migration, app/schemas/memory_migration.py
[OUTPUT] MemoryMigrationService, get_memory_migration_service

Business service mediating digital sovereign asset package export, restore, and competitor ingestion.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from threading import Lock

from myrm_agent_harness.toolkits.memory.sovereign_migration import (
    AssetCategory,
    CompetitorDetectResult,
    CompetitorImportResult,
    CompetitorIngestionAdapter,
    CompetitorType,
    ExportBundleRequest,
    ExportBundleResult,
    RestoreBundleRequest,
    RestoreBundleResult,
    SovereignBundleArchiver,
    SovereignBundleRestorer,
)

from app.schemas.memory_migration import (
    CompetitorDetectResponseDTO,
    CompetitorIngestRequestDTO,
    CompetitorIngestResponseDTO,
    ExportBundleRequestDTO,
    ExportBundleResponseDTO,
    RestoreBundleRequestDTO,
    RestoreBundleResponseDTO,
)

logger = logging.getLogger(__name__)


class MemoryMigrationService:
    """Service managing sovereign asset packaging, verified restore, and competitor migration."""

    def __init__(
        self,
        archiver: SovereignBundleArchiver | None = None,
        restorer: SovereignBundleRestorer | None = None,
        competitor_adapter: CompetitorIngestionAdapter | None = None,
        default_storage_dir: Path | str | None = None,
    ) -> None:
        self._archiver = archiver or SovereignBundleArchiver()
        self._restorer = restorer or SovereignBundleRestorer()
        self._competitor_adapter = competitor_adapter or CompetitorIngestionAdapter()

        if default_storage_dir is not None:
            self._default_storage_dir = Path(default_storage_dir).resolve()
        else:
            base_dir_env = os.getenv("MYRM_MEMORY_STORAGE_DIR", ".myrm")
            self._default_storage_dir = Path(base_dir_env).resolve()

        self._active_backup_lock = Lock()
        logger.info("MemoryMigrationService initialized with storage_dir=%s", self._default_storage_dir)

    def export_bundle(self, request: ExportBundleRequestDTO) -> ExportBundleResponseDTO:
        """Atomically create a verified .myrmpkg sovereign asset package."""
        src_dir = (
            Path(request.source_dir).resolve()
            if request.source_dir
            else self._default_storage_dir
        )
        if not src_dir.exists():
            src_dir.mkdir(parents=True, exist_ok=True)

        if request.output_bundle_path:
            out_path = Path(request.output_bundle_path).resolve()
        else:
            backups_dir = self._default_storage_dir / "backups"
            backups_dir.mkdir(parents=True, exist_ok=True)
            ts = time.strftime("%Y%m%d%H%M%S")
            out_path = backups_dir / f"myrmpkg-{ts}.myrmpkg"

        # Map category strings to enum
        category_map: dict[str, AssetCategory] = {
            "wiki_memory": AssetCategory.WIKI_MEMORY,
            "sqlite_database": AssetCategory.SQLITE_DATABASE,
            "handoff_record": AssetCategory.HANDOFF_RECORD,
            "unload_snapshot": AssetCategory.UNLOAD_SNAPSHOT,
            "agent_rule": AssetCategory.AGENT_RULE,
            "custom_skill": AssetCategory.CUSTOM_SKILL,
            "prompt_playbook": AssetCategory.PROMPT_PLAYBOOK,
        }
        typed_cats = [
            category_map[cat]
            for cat in request.include_categories
            if cat in category_map
        ]
        if not typed_cats:
            typed_cats = [
                AssetCategory.WIKI_MEMORY,
                AssetCategory.SQLITE_DATABASE,
                AssetCategory.HANDOFF_RECORD,
                AssetCategory.UNLOAD_SNAPSHOT,
                AssetCategory.AGENT_RULE,
                AssetCategory.CUSTOM_SKILL,
            ]

        harness_req = ExportBundleRequest(
            source_dir=str(src_dir),
            output_bundle_path=str(out_path),
            include_categories=typed_cats,
            custom_description=request.custom_description,
        )

        with self._active_backup_lock:
            result: ExportBundleResult = self._archiver.export_bundle(harness_req)

        return ExportBundleResponseDTO(
            success=result.success,
            bundle_path=result.bundle_path,
            package_id=result.package_id,
            asset_count=result.asset_count,
            total_bytes=result.total_bytes,
            sha256=result.sha256,
        )

    def restore_bundle(self, request: RestoreBundleRequestDTO) -> RestoreBundleResponseDTO:
        """Unpack, checksum-verify, remap paths, and restore a .myrmpkg archive."""
        target_dir = (
            Path(request.target_destination_dir).resolve()
            if request.target_destination_dir
            else self._default_storage_dir
        )
        ws_root = (
            Path(request.current_workspace_root).resolve()
            if request.current_workspace_root
            else Path.cwd().resolve()
        )

        harness_req = RestoreBundleRequest(
            bundle_path=request.bundle_path,
            target_destination_dir=str(target_dir),
            current_workspace_root=str(ws_root),
            overwrite_existing=request.overwrite_existing,
        )

        with self._active_backup_lock:
            result: RestoreBundleResult = self._restorer.restore_bundle(harness_req)

        return RestoreBundleResponseDTO(
            success=result.success,
            package_id=result.package_id,
            restored_assets=result.restored_assets,
            remapped_paths_count=result.remapped_paths_count,
            source_workspace_root=result.source_workspace_root,
            target_workspace_root=result.target_workspace_root,
        )

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
            raise ValueError(
                f"Unsupported competitor type '{request.competitor}'. Supported: {list(type_map.keys())}"
            )

        target_dir = (
            Path(request.target_destination_dir).resolve()
            if request.target_destination_dir
            else self._default_storage_dir
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
