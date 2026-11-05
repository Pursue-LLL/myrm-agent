"""[INPUT]
- pydantic::BaseModel (POS: request/response model base)

[OUTPUT]
- MemoryCommandMigrationSourceManifestItem, MemoryCommandMigrationProvenance

[POS]
Memory command center schemas: migration manifest and provenance.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.memory.import_sources import ImportSource

MemoryCommandMigrationImportSource = ImportSource


class MemoryCommandMigrationSourceManifestItem(BaseModel):
    """Server-declared migration source metadata for UI routing/rendering."""

    id: str
    display_name: str
    import_source: MemoryCommandMigrationImportSource
    discover_modes: list[Literal["local_scan", "zip_upload"]] = Field(default_factory=list)
    deep_link_enabled: bool = True


class MemoryCommandMigrationProvenance(BaseModel):
    """Import/export provenance summary for memory migration visibility."""

    source_manifest: list[MemoryCommandMigrationSourceManifestItem] = Field(default_factory=list)
    source_manifest_authoritative: bool = True
    tracked_imports: int = 0
    unmapped_items: int = 0
    coverage_status: Literal["not_tracked", "partial", "complete"] = "not_tracked"
    last_import_batch_id: str | None = None
    verification_recommended: bool = False
    last_import_diagnostic_status: str | None = None
    last_import_diagnostic_run_id: str | None = None
    last_import_readiness_status: Literal["ready", "warning", "critical"] | None = None
    last_import_first_turn_outcome: Literal["success", "failed", "no_output"] | None = None
    cleanup_pending_sessions: int = 0
    cleanup_confirmed_sessions: int = 0
    cleanup_expired_sessions: int = 0
    cleanup_rolled_back_sessions: int = 0
    cleanup_retention_days: int = 7
