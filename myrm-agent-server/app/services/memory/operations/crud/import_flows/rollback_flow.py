"""Memory import rollback handlers.

[INPUT]
app.services.memory.imports.import_rollback (POS: 记忆导入回滚)

[OUTPUT]
dry_run_rollback_import_memories, rollback_import_memories: rollback preview
and execution for a recorded import batch.

[POS]
Undo half of the import lifecycle, driven by the ledger entries the confirm flow
wrote so a user can always take a migration back.
"""

from __future__ import annotations

import logging

from fastapi import Depends, HTTPException
from myrm_agent_harness.toolkits.memory import (
    MemoryManager,
)

from app.database.connection import get_session
from app.schemas.memory.archive import (
    MemoryImportRollbackPreviewResponse,
    MemoryImportRollbackRequest,
    MemoryImportRollbackResponse,
)
from app.services.memory.imports.import_sessions import (
    MemoryImportSessionError,
    MemoryImportSessionService,
)
from app.services.memory.manager_deps import get_crud_memory_manager

logger = logging.getLogger(__name__)


async def dry_run_rollback_import_memories(
    body: MemoryImportRollbackRequest,
    manager: MemoryManager = Depends(get_crud_memory_manager),
) -> MemoryImportRollbackPreviewResponse:
    """Preview rollback impact for a confirmed memory import batch."""

    async with get_session() as db:
        try:
            result = await MemoryImportSessionService(db).preview_rollback(
                manager=manager,
                dry_run_id=body.dry_run_id,
                import_batch_id=body.import_batch_id,
            )
        except MemoryImportSessionError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return MemoryImportRollbackPreviewResponse(
        import_batch_id=result.import_batch_id,
        source=result.source,
        total_items=result.total_items,
        reversible_items=result.reversible_items,
        items_by_type=result.items_by_type,
        profile_keys=result.profile_keys,
        warnings=[
            {
                "code": warning.code,
                "severity": warning.severity,
                "params": warning.params,
            }
            for warning in result.warnings
        ],
        skipped_items=result.skipped_items,
        conflict_items=result.conflict_items,
        missing_items=result.missing_items,
    )


async def rollback_import_memories(
    body: MemoryImportRollbackRequest,
    manager: MemoryManager = Depends(get_crud_memory_manager),
) -> MemoryImportRollbackResponse:
    """Rollback a confirmed memory import batch from its server-bound session."""
    from app.services.memory.imports.import_ledger import MemoryImportLedgerService
    from app.services.migration.instruction_rollback import (
        rollback_instruction_for_batch_metadata,
    )

    instructions_rolled_back = False
    imported_agent_deleted = False
    async with get_session() as db:
        try:
            ledger = MemoryImportLedgerService(db)
            batch = await ledger.get_batch(
                dry_run_id=body.dry_run_id,
                import_batch_id=body.import_batch_id,
            )
            result = await MemoryImportSessionService(db).rollback_import(
                manager=manager,
                dry_run_id=body.dry_run_id,
                import_batch_id=body.import_batch_id,
            )
            if batch is not None:
                metadata = batch.metadata_json if isinstance(batch.metadata_json, dict) else {}
                instructions_rolled_back = await rollback_instruction_for_batch_metadata(
                    metadata,
                    delete_imported_agent=body.delete_imported_agent,
                )
                cron_raw = metadata.get("cron_rollback")
                if isinstance(cron_raw, dict):
                    from app.services.migration.hermes.hermes_cron_migration import (
                        rollback_hermes_cron_migration,
                    )

                    await rollback_hermes_cron_migration(cron_raw)
                if body.delete_imported_agent and instructions_rolled_back:
                    raw = metadata.get("instruction_rollback")
                    if isinstance(raw, dict) and bool(raw.get("agent_created")):
                        imported_agent_deleted = True
        except MemoryImportSessionError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return MemoryImportRollbackResponse(
        import_batch_id=result.import_batch_id,
        rolled_back=result.rolled_back,
        total_rolled_back=result.total_rolled_back,
        source=result.source,
        conflict_items=result.conflict_items,
        missing_items=result.missing_items,
        failed_items=result.failed_items,
        deleted_refs=result.deleted_refs,
        missing_refs=result.missing_refs,
        forbidden_refs=result.forbidden_refs,
        failed_refs=result.failed_refs,
        integrity_status=result.integrity_status,
        instructions_rolled_back=instructions_rolled_back,
        imported_agent_deleted=imported_agent_deleted,
    )
