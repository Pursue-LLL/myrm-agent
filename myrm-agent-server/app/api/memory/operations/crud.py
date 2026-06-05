"""Memory CRUD HTTP routes — thin transport layer."""

from __future__ import annotations

from fastapi import APIRouter

from app.schemas.memory.archive import (
    MemoryArchiveDryRunResponse,
    MemoryArchiveExportResponse,
    MemoryImportConfirmResponse,
    MemoryImportDryRunResponse,
    MemoryImportResponse,
    MemoryImportRollbackPreviewResponse,
    MemoryImportRollbackResponse,
)
from app.schemas.memory.crud import (
    MemoryExportResponse,
    MemoryItem,
    MemoryListPaginatedResponse,
    MemorySearchResponse,
    MemoryStatsResponse,
    PreferenceFacetListResponse,
    RateMemoryResponse,
    TasteSummaryResponse,
)
from app.services.memory.operations import crud_handlers as handlers

router = APIRouter()

router.get("/", response_model=MemoryListPaginatedResponse)(handlers.list_memories_paginated)
router.post("/", response_model=MemoryItem)(handlers.create_memory)
router.put("/{memory_type}/{memory_id}", response_model=MemoryItem)(handlers.update_memory)
router.post("/{memory_id}/correct", response_model=MemoryItem)(handlers.correct_memory)
router.delete("/all")(handlers.delete_all_memories)
router.delete("/{memory_id}")(handlers.delete_memory_by_id)
router.get("/trash", response_model=MemoryListPaginatedResponse)(handlers.list_trash_memories)
router.post("/trash/{memory_id}/restore", response_model=MemoryItem)(handlers.restore_trashed_memory)
router.delete("/trash/{memory_id}/purge")(handlers.purge_trashed_memory)
router.get("/search", response_model=MemorySearchResponse)(handlers.search_memories)
router.get("/stats", response_model=MemoryStatsResponse)(handlers.get_memory_stats)
router.get("/context")(handlers.get_memory_context)
router.get("/export", response_model=MemoryExportResponse)(handlers.export_memories)
router.get("/archive/export", response_model=MemoryArchiveExportResponse)(handlers.export_memory_archive)
router.post("/archive/dry-run", response_model=MemoryArchiveDryRunResponse)(handlers.dry_run_memory_archive)
router.post("/import", response_model=MemoryImportResponse)(handlers.import_memories)
router.post("/import/dry-run", response_model=MemoryImportDryRunResponse)(handlers.dry_run_import_memories)
router.post("/import/confirm", response_model=MemoryImportConfirmResponse)(handlers.confirm_import_memories)
router.post("/import/rollback/dry-run", response_model=MemoryImportRollbackPreviewResponse)(
    handlers.dry_run_rollback_import_memories
)
router.post("/import/rollback", response_model=MemoryImportRollbackResponse)(handlers.rollback_import_memories)
router.post("/{memory_id}/rate", response_model=RateMemoryResponse)(handlers.rate_memory)
router.post("/undo-consolidation")(handlers.undo_consolidation)
router.patch("/{memory_id}/status", response_model=MemoryItem)(handlers.update_memory_status)
router.get("/taste-summary", response_model=TasteSummaryResponse)(handlers.get_taste_summary)
router.get("/preferences", response_model=PreferenceFacetListResponse)(handlers.list_preferences)
router.post("/preferences/{facet_id}/pin")(handlers.pin_preference)
router.post("/preferences/{facet_id}/forget")(handlers.forget_preference)
router.post("/preferences/{facet_id}/unpin")(handlers.unpin_preference)
router.post("/preferences/{facet_id}/unforget")(handlers.unforget_preference)
