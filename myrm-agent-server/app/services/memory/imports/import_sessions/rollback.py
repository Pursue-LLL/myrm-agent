"""[INPUT]
- .base (POS: 共享类型、常量与状态)
- .queries::ImportQueriesMixin (POS: 批次/会话查询)

[OUTPUT]
- RollbackMixin: 回滚预览、执行与不完整回滚恢复

[POS]
`import_sessions/` 的回滚阶段。
"""

from __future__ import annotations

from datetime import UTC, datetime

from myrm_agent_harness.toolkits.memory import (
    MemoryManager,
    MemoryOperationKind,
    MemoryOperationStatus,
    MemoryType,
)

from app.database.models.memory import MemoryImportBatchModel, MemoryImportDryRunModel
from app.services.memory.imports.import_ledger import (
    IMPORT_ITEM_STATUS_CONFLICT,
    IMPORT_ITEM_STATUS_MISSING,
    IMPORT_ITEM_STATUS_ROLLBACK_FAILED,
    IMPORT_ITEM_STATUS_SKIPPED,
)
from app.services.memory.imports.import_rollback import (
    count_profile_conflicts,
    is_imported_memory_item,
    is_imported_profile_item,
    preview_items_by_type,
    rollback_memory_items,
    rollback_preview_warnings,
    rollback_profile_items,
)
from app.services.memory.imports.import_session_models import (
    MemoryImportRollbackPreviewResult,
    MemoryImportRollbackResult,
)

from .base import (
    DRY_RUN_STATUS_ROLLED_BACK,
    MemoryImportSessionBase,
    _rollback_in_progress,
)


class RollbackMixin(MemoryImportSessionBase):
    """回滚预览、执行与不完整回滚恢复。"""

    async def preview_rollback(
        self,
        *,
        manager: MemoryManager,
        dry_run_id: str | None = None,
        import_batch_id: str | None = None,
    ) -> MemoryImportRollbackPreviewResult:
        """Return a content-safe preview for a confirmed import rollback."""

        await self._expire_stale()
        batch = await self._get_confirmed_batch(dry_run_id=dry_run_id, import_batch_id=import_batch_id)
        items = await self._import_ledger.list_items(batch.id)
        profile_items = [item for item in items if is_imported_profile_item(item)]
        profile_conflicts = await count_profile_conflicts(manager, profile_items)
        items_by_type = preview_items_by_type(items, profile_conflicts=profile_conflicts)
        skipped_items = sum(1 for item in items if item.status == IMPORT_ITEM_STATUS_SKIPPED)
        missing_items = sum(1 for item in items if item.status == IMPORT_ITEM_STATUS_MISSING)
        reversible_items = sum(items_by_type.values())
        profile_keys = sorted(item.profile_key for item in profile_items if item.profile_key)
        warnings = rollback_preview_warnings(
            reversible_items=reversible_items,
            profile_keys=profile_keys,
            profile_conflicts=profile_conflicts,
            memory_rows_missing=sum(1 for item in items if is_imported_memory_item(item) and not item.memory_ids_json),
        )

        return MemoryImportRollbackPreviewResult(
            import_batch_id=batch.id,
            source=batch.source,
            total_items=len(items),
            reversible_items=reversible_items,
            items_by_type=items_by_type,
            profile_keys=profile_keys,
            warnings=warnings,
            skipped_items=skipped_items,
            conflict_items=profile_conflicts,
            missing_items=missing_items,
        )


    async def rollback_import(
        self,
        *,
        manager: MemoryManager,
        dry_run_id: str | None = None,
        import_batch_id: str | None = None,
    ) -> MemoryImportRollbackResult:
        """Rollback a confirmed import batch by deleting records tagged with its batch id."""

        await self._expire_stale()
        batch = await self._get_rollback_batch(dry_run_id=dry_run_id, import_batch_id=import_batch_id)
        if _rollback_in_progress(batch):
            return await self._execute_batch_rollback(manager=manager, batch=batch, recovering=True)
        await self.recover_incomplete_rollbacks(manager, exclude_batch_id=batch.id)
        return await self._execute_batch_rollback(manager=manager, batch=batch)


    async def recover_incomplete_rollbacks(self, manager: MemoryManager, *, exclude_batch_id: str | None = None) -> int:
        """Resume batches that were journaled before a process interruption."""

        recovered = 0
        for batch in await self._import_ledger.list_incomplete_rollbacks():
            if batch.id == exclude_batch_id:
                continue
            await self._execute_batch_rollback(manager=manager, batch=batch, recovering=True)
            recovered += 1
        return recovered


    async def _execute_batch_rollback(
        self,
        *,
        manager: MemoryManager,
        batch: MemoryImportBatchModel,
        recovering: bool = False,
    ) -> MemoryImportRollbackResult:
        items = await self._import_ledger.list_items(batch.id)
        now = datetime.now(UTC)
        if not recovering:
            self._import_ledger.begin_batch_rollback(batch, started_at=now)
            await self._db.commit()
        memory_result = await rollback_memory_items(manager, self._import_ledger, items, rolled_back_at=now)
        rolled_back = dict(memory_result.rolled_back)
        profile_result = await rollback_profile_items(manager, self._import_ledger, items, rolled_back_at=now)
        if profile_result.rolled_back > 0:
            rolled_back[MemoryType.PROFILE.value] = profile_result.rolled_back
        total = sum(rolled_back.values())
        failed_items = sum(1 for item in items if item.status == IMPORT_ITEM_STATUS_ROLLBACK_FAILED)
        missing_items = sum(1 for item in items if item.status == IMPORT_ITEM_STATUS_MISSING)
        conflict_items = profile_result.conflicts
        self._import_ledger.mark_batch_rollback(
            batch,
            rolled_back_count=total,
            conflict_count=conflict_items,
            missing_count=missing_items,
            failed_count=failed_items,
            rolled_back_at=now,
        )
        await self._mark_dry_run_rolled_back(batch, total, now)
        integrity_status = await self._rollback_integrity_status(manager=manager, batch=batch)
        event_status = (
            MemoryOperationStatus.ERROR
            if failed_items > 0
            else MemoryOperationStatus.WARNING
            if conflict_items > 0 or missing_items > 0
            else MemoryOperationStatus.SUCCESS
        )
        await self._ledger.record_event(
            kind=MemoryOperationKind.FORGET,
            status=event_status,
            summary="Memory import batch rolled back.",
            source="memory_import_session",
            target_kind="memory_import",
            target_id=batch.dry_run_id,
            correlation_id=batch.id,
            metadata={
                "dry_run_id": batch.dry_run_id,
                "payload_hash": batch.payload_hash,
                "import_batch_id": batch.id,
                "rolled_back_count": total,
                "conflict_items": conflict_items,
                "missing_items": missing_items,
                "failed_items": failed_items,
                "integrity_status": integrity_status,
                "recovered": recovering,
                "source": batch.source,
            },
        )
        await self._db.commit()
        return MemoryImportRollbackResult(
            import_batch_id=batch.id,
            rolled_back=rolled_back,
            total_rolled_back=total,
            source=batch.source,
            conflict_items=conflict_items,
            missing_items=missing_items,
            failed_items=failed_items,
            deleted_refs=memory_result.deleted_refs,
            missing_refs=memory_result.missing_refs,
            forbidden_refs=memory_result.forbidden_refs,
            failed_refs=memory_result.failed_refs,
            integrity_status=integrity_status,
        )


    async def _mark_dry_run_rolled_back(
        self,
        batch: MemoryImportBatchModel,
        total_rolled_back: int,
        rolled_back_at: datetime,
    ) -> None:
        row = await self._db.get(MemoryImportDryRunModel, batch.dry_run_id)
        if row is None:
            return
        row.status = DRY_RUN_STATUS_ROLLED_BACK
        row.metadata_json = {
            **(row.metadata_json or {}),
            "rolled_back_at": rolled_back_at.isoformat(),
            "rolled_back_count": total_rolled_back,
            "transaction_ledger_summary": {
                "version": 2,
                "import_batch_id": batch.id,
                "item_count": batch.transaction_item_count,
                "rolled_back_count": total_rolled_back,
            },
        }


    async def _rollback_integrity_status(self, *, manager: MemoryManager, batch: MemoryImportBatchModel) -> str:
        refs = await manager.list_memory_refs_by_metadata("import_batch_id", batch.id)
        remaining_refs = sum(len(values) for values in refs.values())
        if remaining_refs > 0:
            return "critical"
        items = await self._import_ledger.list_items(batch.id)
        if any(
            item.status in {IMPORT_ITEM_STATUS_CONFLICT, IMPORT_ITEM_STATUS_ROLLBACK_FAILED, IMPORT_ITEM_STATUS_MISSING}
            for item in items
        ):
            return "warning"
        return "ready"
