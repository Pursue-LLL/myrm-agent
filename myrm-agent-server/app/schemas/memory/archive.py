"""Memory archive and import shared schemas.

[INPUT]
app.schemas.memory.crud::MEMORY_EXPORT_VERSION (POS: 记忆 CRUD 共享 Schema)
myrm_agent_harness.toolkits.memory::* (POS: framework archive and import DTOs)

[OUTPUT]
Archive and server-bound import request-response models.

[POS]
记忆归档与导入共享 Schema。api 与 services 层共用。
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from myrm_agent_harness.toolkits.memory import (
    MemoryArchiveDryRunResult,
    MemoryArchivePayload,
    MemoryArchiveRestoreDryRunResult,
    MemoryArchiveRestoreResult,
    MemoryArchiveRestoreRollbackPreview,
    MemoryArchiveRestoreRollbackResult,
    MemoryArchiveSectionName,
    MemoryImportDryRunResult,
)
from pydantic import BaseModel, Field

from app.schemas.memory.crud import MEMORY_EXPORT_VERSION


class MemoryImportRequest(BaseModel):
    """Request to import memories from exported data."""

    version: int = Field(MEMORY_EXPORT_VERSION, description="Export schema version")
    data: dict[str, list[dict[str, object]]] = Field(
        ..., description="Exported memory data keyed by memory type"
    )
    skip_duplicates: bool = Field(True, description="Skip duplicate memories")


class MemoryArchiveExportResponse(BaseModel):
    """Response for a single-sandbox memory archive export."""

    archive: MemoryArchivePayload


class MemoryArchiveDryRunRequest(BaseModel):
    """Request to validate a memory archive before restore/import."""

    archive: dict[str, object] = Field(..., description="Raw Myrm memory archive payload")


class MemoryArchiveDryRunResponse(BaseModel):
    """Content-safe memory archive import preview."""

    result: MemoryArchiveDryRunResult


class MemoryArchiveRestoreDryRunRequest(BaseModel):
    """Request to preview a Myrm archive restore."""

    archive: dict[str, object] = Field(..., description="Raw Myrm memory archive payload")
    sections: list[MemoryArchiveSectionName] | None = Field(None, description="Archive sections selected for restore")


class MemoryArchiveRestoreDryRunResponse(BaseModel):
    """Content-safe archive restore preview."""

    result: MemoryArchiveRestoreDryRunResult


class MemoryArchiveRestoreConfirmRequest(BaseModel):
    """Request to execute a reviewed archive restore."""

    archive: dict[str, object] = Field(..., description="Raw Myrm memory archive payload")
    payload_hash: str = Field(..., min_length=64, max_length=64, description="Payload hash returned by restore dry-run")
    plan_hash: str = Field(..., min_length=64, max_length=64, description="Plan hash returned by restore dry-run")
    sections: list[MemoryArchiveSectionName] | None = Field(None, description="Archive sections selected for restore")
    skip_duplicates: bool = Field(True, description="Skip duplicate native memory rows")


class MemoryArchiveRestoreConfirmResponse(BaseModel):
    """Archive restore execution response."""

    result: MemoryArchiveRestoreResult


class MemoryArchiveRestoreRollbackRequest(BaseModel):
    """Request to inspect or rollback a restore batch."""

    restore_batch_id: str


class MemoryArchiveRestoreRollbackPreviewResponse(BaseModel):
    """Content-safe archive restore rollback preview."""

    result: MemoryArchiveRestoreRollbackPreview


class MemoryArchiveRestoreRollbackResponse(BaseModel):
    """Archive restore rollback response."""

    result: MemoryArchiveRestoreRollbackResult


class MigrationLanePreviewItem(BaseModel):
    """Content-safe four-lane migration preview row."""

    lane: str
    status: str
    label: str
    detail: str


class MemoryImportMigrationOptions(BaseModel):
    """Competitor migration binding options (Local/Tauri wizard)."""

    target_agent_id: str | None = Field(
        None,
        description="Existing agent to receive persona; clones when omitted",
    )
    clone_from_agent_id: str = Field(
        "builtin-general",
        description="Built-in agent profile used as clone template",
    )
    include_episodic: bool = Field(
        False,
        description="Import OpenClaw session summaries into episodic memory",
    )
    apply_global_instructions: bool = Field(
        True,
        description="Append project-level instructions to global user instructions",
    )


class MemoryImportDryRunRequest(BaseModel):
    """Request to preview a memory import without persisting data."""

    source: Literal[
        "auto",
        "native_json",
        "myrm_archive",
        "agentmemory",
        "gbrain",
        "memweaver",
        "claude_code_jsonl",
        "hermes",
        "openclaw",
        "cursor_rules",
        "codex",
        "claude",
    ] = "auto"
    payload: dict[str, object] = Field(..., description="Raw memory export payload")
    skip_duplicates: bool = Field(True, description="Preview duplicate-safe import behavior")
    migration: MemoryImportMigrationOptions | None = Field(
        None,
        description="Competitor migration binding (instruction/memory lanes)",
    )


class MemoryImportDryRunResponse(BaseModel):
    """Content-safe memory import preview bound to a server-side review session."""

    dry_run_id: str
    payload_hash: str
    expires_at: datetime
    result: MemoryImportDryRunResult
    pending_skills: list[dict[str, object]] = Field(default_factory=list)
    coverage_items: list[dict[str, str]] = Field(default_factory=list)
    migration_lanes: list[MigrationLanePreviewItem] = Field(default_factory=list)
    instruction_preview_persona: str | None = Field(
        None,
        description="Truncated persona preview for competitor migration",
    )
    instruction_preview_rule_names: list[str] = Field(default_factory=list)
    instruction_total_chars: int = Field(
        0,
        description="Total character count of instruction-lane content (persona + global + rules)",
    )
    providers_configured: bool = Field(
        True,
        description="Whether model provider slots exist for competitor API key import",
    )


class MemoryImportConfirmRequest(BaseModel):
    """Request to confirm a server-bound memory import dry-run."""

    dry_run_id: str = Field(..., description="Server-side dry-run review session id")
    skip_duplicates: bool = Field(True, description="Skip duplicate memories")
    apply_instructions: bool = Field(
        True,
        description="Apply instruction lane from the bound dry-run session",
    )


class MemoryImportRollbackRequest(BaseModel):
    """Request to rollback a confirmed server-bound memory import."""

    dry_run_id: str | None = Field(None, description="Server-side dry-run review session id")
    import_batch_id: str | None = Field(None, description="Confirmed import batch id")
    delete_imported_agent: bool = Field(
        False,
        description="When true, delete the agent created by this competitor import batch",
    )


class MemoryImportRollbackWarning(BaseModel):
    """Structured rollback warning for localized clients."""

    code: str
    severity: Literal["info", "warning", "error"] = "warning"
    params: dict[str, str | int | float | bool] = Field(default_factory=dict)


class MemoryImportRollbackRef(BaseModel):
    """Content-safe rollback mutation reference."""

    memory_type: str
    memory_id: str
    backend: str = ""
    reason: str = ""


class MemoryImportResponse(BaseModel):
    """Response for memory import endpoint."""

    imported: dict[str, int]
    total_imported: int


class MemoryImportConfirmResponse(MemoryImportResponse):
    """Response for a server-bound memory import confirmation."""

    import_batch_id: str
    payload_hash: str
    source: str
    transaction_items: int = 0
    diagnostic_status: str | None = None
    diagnostic_run_id: str | None = None
    target_agent_id: str | None = None
    agent_created: bool = False
    global_instructions_updated: bool = False
    workspace_rules_written: int = 0
    workspace_rules_skipped: int = 0


class MemoryImportRollbackPreviewResponse(BaseModel):
    """Content-safe rollback preview for a confirmed server-bound import."""

    import_batch_id: str
    source: str
    total_items: int
    reversible_items: int
    items_by_type: dict[str, int]
    profile_keys: list[str] = Field(default_factory=list)
    warnings: list[MemoryImportRollbackWarning] = Field(default_factory=list)
    skipped_items: int = 0
    conflict_items: int = 0
    missing_items: int = 0
    requires_confirmation: bool = True


class MemoryImportRollbackResponse(BaseModel):
    """Response for a server-bound memory import rollback."""

    import_batch_id: str
    rolled_back: dict[str, int]
    total_rolled_back: int
    source: str
    conflict_items: int = 0
    missing_items: int = 0
    failed_items: int = 0
    deleted_refs: list[MemoryImportRollbackRef] = Field(default_factory=list)
    missing_refs: list[MemoryImportRollbackRef] = Field(default_factory=list)
    forbidden_refs: list[MemoryImportRollbackRef] = Field(default_factory=list)
    failed_refs: list[MemoryImportRollbackRef] = Field(default_factory=list)
    integrity_status: str = "not_checked"
    instructions_rolled_back: bool = False
    imported_agent_deleted: bool = False
