"""Single-sandbox Memory Archive restore service.

[INPUT]
myrm_agent_harness.toolkits.memory::MemoryArchivePayload, MemoryManager (POS: framework archive DTOs)
app.database.models.memory::* (POS: 记忆域 ORM 模型)

[OUTPUT]
MemoryArchiveRestoreService: dry-run, safe-merge restore, rollback preview, and rollback for Myrm Memory Archive.

[POS]
单用户归档恢复服务。只在当前 local/Tauri/单用户 sandbox 服务内恢复业务内容；
不包含多租户或控制平面语义，control-plane 只能消费内容盲 metadata。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

from myrm_agent_harness.toolkits.memory import (
    MemoryArchivePayload,
    MemoryArchiveRestoreDryRunResult,
    MemoryArchiveRestoreResult,
    MemoryArchiveRestoreRollbackPreview,
    MemoryArchiveRestoreRollbackResult,
    MemoryArchiveSectionName,
    MemoryManager,
    MemoryOperationKind,
    MemoryReliabilityStatus,
)
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.memory import MemoryArchiveRestoreBatchModel, MemoryArchiveRestoreItemModel
from app.services.memory.archive_restore_common import (
    RESTORE_BATCH_STATUS_CONFIRMED,
    RESTORE_BATCH_STATUS_FAILED,
    RESTORE_BATCH_STATUS_IN_PROGRESS,
    RESTORE_BATCH_STATUS_PARTIAL,
    RESTORE_BATCH_STATUS_ROLLBACK_FAILED,
    RESTORE_BATCH_STATUS_ROLLBACK_IN_PROGRESS,
    RESTORE_BATCH_STATUS_ROLLED_BACK,
    RESTORE_ITEM_STATUS_CONFLICT,
    RESTORE_ITEM_STATUS_FAILED,
    RESTORE_ITEM_STATUS_MISSING,
    RESTORE_ITEM_STATUS_RESTORED,
    RESTORE_ITEM_STATUS_ROLLED_BACK,
    RESTORE_ITEM_STATUS_SKIPPED,
    MemoryArchiveRestoreError,
    add_restore_item,
    make_ref,
    operation_status,
    selected_sections,
)
from app.services.memory.archive_restore_executor import MemoryArchiveRestoreExecutor
from app.services.memory.archive_restore_planner import MemoryArchiveRestorePlanner
from app.services.memory.archive_restore_rollback import MemoryArchiveRestoreRollbacker
from app.services.memory.operation_ledger import MemoryOperationLedgerService

ArchiveRestoreHealthStatus = Literal["ready", "warning", "critical"]


@dataclass(frozen=True)
class ArchiveRestoreHealth:
    """Content-free archive restore journal and rollback health counters."""

    in_progress_batches: int = 0
    failed_batches: int = 0
    partial_batches: int = 0
    rollback_in_progress_batches: int = 0
    rollback_failed_batches: int = 0
    missing_items: int = 0
    failed_items: int = 0

    @property
    def status(self) -> ArchiveRestoreHealthStatus:
        if self.failed_batches > 0 or self.rollback_failed_batches > 0 or self.failed_items > 0:
            return "critical"
        if (
            self.in_progress_batches > 0
            or self.partial_batches > 0
            or self.rollback_in_progress_batches > 0
            or self.missing_items > 0
        ):
            return "warning"
        return "ready"


class MemoryArchiveRestoreService:
    """Plans, executes, and rolls back safe-merge Myrm archive restores."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        self._ledger = MemoryOperationLedgerService(db)
        self._planner = MemoryArchiveRestorePlanner(db)
        self._executor = MemoryArchiveRestoreExecutor(db)
        self._rollbacker = MemoryArchiveRestoreRollbacker(db)

    async def dry_run_restore(
        self,
        payload: dict[str, object],
        *,
        sections: Sequence[MemoryArchiveSectionName] | None = None,
    ) -> MemoryArchiveRestoreDryRunResult:
        """Build a content-safe restore plan without mutating state."""

        return await self._planner.dry_run_restore(payload, sections=sections)

    async def restore_archive(
        self,
        payload: dict[str, object],
        *,
        manager: MemoryManager,
        sections: Sequence[MemoryArchiveSectionName] | None = None,
        skip_duplicates: bool = True,
        expected_payload_hash: str,
        expected_plan_hash: str,
    ) -> MemoryArchiveRestoreResult:
        """Restore selected archive sections using safe merge semantics."""

        archive = MemoryArchivePayload.model_validate(payload)
        preview = await self.dry_run_restore(payload, sections=sections)
        _validate_review_hashes(
            preview=preview,
            expected_payload_hash=expected_payload_hash,
            expected_plan_hash=expected_plan_hash,
        )
        if preview.plan.restorable_items <= 0:
            raise MemoryArchiveRestoreError("Archive restore does not contain any restorable items.")
        if preview.plan.blocked_items > 0:
            raise MemoryArchiveRestoreError("Archive restore is blocked by security preflight.", status_code=422)

        await self.recover_incomplete_restores(manager)
        payload_hash = preview.payload_hash
        batch_id = f"memory-archive-restore:{uuid4().hex}"
        now = datetime.now(UTC)
        batch = MemoryArchiveRestoreBatchModel(
            id=batch_id,
            source="myrm_archive",
            status=RESTORE_BATCH_STATUS_IN_PROGRESS,
            payload_hash=payload_hash,
            plan_hash=preview.plan.plan_hash,
            created_at=now,
            confirmed_at=now,
            metadata_json={
                "archive_created_at": archive.manifest.created_at,
                "archive_version": archive.manifest.version,
                "selected_sections": list(selected_sections(sections)),
                "restore_journal": {
                    "status": RESTORE_BATCH_STATUS_IN_PROGRESS,
                    "started_at": now.isoformat(),
                    "payload_hash": payload_hash,
                    "plan_hash": preview.plan.plan_hash,
                },
            },
        )
        self._db.add(batch)
        await self._db.commit()
        try:
            refs = await self._executor.restore_sections(
                archive=archive,
                batch_id=batch_id,
                payload_hash=payload_hash,
                manager=manager,
                sections=sections,
                skip_duplicates=skip_duplicates,
            )
        except Exception as exc:
            await self._mark_restore_apply_failed(batch_id, exc)
            raise MemoryArchiveRestoreError("Archive restore failed during journaled apply.") from exc
        restored = _count_by_section(refs, RESTORE_ITEM_STATUS_RESTORED)
        skipped_items = _count_status(refs, RESTORE_ITEM_STATUS_SKIPPED)
        conflict_items = _count_status(refs, RESTORE_ITEM_STATUS_CONFLICT)
        failed_items = _count_status(refs, RESTORE_ITEM_STATUS_FAILED)
        batch = await self._get_batch(batch_id)
        batch.restored_count = sum(restored.values())
        batch.skipped_count = skipped_items
        batch.conflict_count = conflict_items
        batch.failed_count = failed_items
        batch.transaction_item_count = len(refs)
        batch.status = _restore_batch_status(total_restored=batch.restored_count, failed_items=failed_items)
        batch.metadata_json = {
            **(batch.metadata_json or {}),
            "restore_journal": {
                "status": batch.status,
                "completed_at": datetime.now(UTC).isoformat(),
                "payload_hash": payload_hash,
                "plan_hash": preview.plan.plan_hash,
            },
        }
        await self._ledger.record_event(
            kind=MemoryOperationKind.IMPORT_MEMORY,
            status=operation_status(conflict_items=conflict_items, failed_items=failed_items),
            summary="Memory archive restore completed.",
            source="memory_archive_restore",
            target_kind="memory_archive_restore",
            target_id=batch_id,
            correlation_id=batch_id,
            metadata={
                "restore_batch_id": batch_id,
                "payload_hash": payload_hash,
                "plan_hash": preview.plan.plan_hash,
                "restored_count": batch.restored_count,
                "skipped_items": skipped_items,
                "conflict_items": conflict_items,
                "failed_items": failed_items,
            },
        )
        await self._db.commit()
        return MemoryArchiveRestoreResult(
            restore_batch_id=batch_id,
            payload_hash=payload_hash,
            plan_hash=preview.plan.plan_hash,
            restored=restored,
            total_restored=batch.restored_count,
            skipped_items=skipped_items,
            conflict_items=conflict_items,
            failed_items=failed_items,
            warnings=preview.plan.warning_codes,
            mutation_refs=refs,
        )

    async def preview_rollback(self, restore_batch_id: str) -> MemoryArchiveRestoreRollbackPreview:
        """Return a content-safe rollback preview for a restore batch."""

        await self._get_batch(restore_batch_id)
        return await self._rollbacker.preview(restore_batch_id)

    async def save_post_restore_diagnostic(
        self,
        *,
        restore_batch_id: str,
        diagnostic_run_id: str,
        diagnostic_status: str,
        failed_count: int,
    ) -> None:
        """Attach automatic post-restore diagnostics to the content-blind restore batch ledger."""

        batch = await self._get_batch(restore_batch_id)
        batch.metadata_json = {
            **(batch.metadata_json or {}),
            "post_restore_diagnostic": {
                "run_id": diagnostic_run_id,
                "status": diagnostic_status,
                "failed_count": failed_count,
                "completed_at": datetime.now(UTC).isoformat(),
            },
        }
        await self._db.commit()

    async def restore_health(self) -> ArchiveRestoreHealth:
        """Return content-free archive restore journal and item health counters."""

        batch_result = await self._db.execute(
            select(MemoryArchiveRestoreBatchModel.status, func.count())
            .where(
                MemoryArchiveRestoreBatchModel.status.in_(
                    [
                        RESTORE_BATCH_STATUS_IN_PROGRESS,
                        RESTORE_BATCH_STATUS_FAILED,
                        RESTORE_BATCH_STATUS_PARTIAL,
                        RESTORE_BATCH_STATUS_ROLLBACK_IN_PROGRESS,
                        RESTORE_BATCH_STATUS_ROLLBACK_FAILED,
                    ]
                )
            )
            .group_by(MemoryArchiveRestoreBatchModel.status)
        )
        batch_counts = {str(status): int(count) for status, count in batch_result.all()}
        item_result = await self._db.execute(
            select(MemoryArchiveRestoreItemModel.status, func.count())
            .where(MemoryArchiveRestoreItemModel.status.in_([RESTORE_ITEM_STATUS_MISSING, RESTORE_ITEM_STATUS_FAILED]))
            .group_by(MemoryArchiveRestoreItemModel.status)
        )
        item_counts = {str(status): int(count) for status, count in item_result.all()}
        return ArchiveRestoreHealth(
            in_progress_batches=batch_counts.get(RESTORE_BATCH_STATUS_IN_PROGRESS, 0),
            failed_batches=batch_counts.get(RESTORE_BATCH_STATUS_FAILED, 0),
            partial_batches=batch_counts.get(RESTORE_BATCH_STATUS_PARTIAL, 0),
            rollback_in_progress_batches=batch_counts.get(RESTORE_BATCH_STATUS_ROLLBACK_IN_PROGRESS, 0),
            rollback_failed_batches=batch_counts.get(RESTORE_BATCH_STATUS_ROLLBACK_FAILED, 0),
            missing_items=item_counts.get(RESTORE_ITEM_STATUS_MISSING, 0),
            failed_items=item_counts.get(RESTORE_ITEM_STATUS_FAILED, 0),
        )

    async def rollback_restore(
        self,
        restore_batch_id: str,
        *,
        manager: MemoryManager,
    ) -> MemoryArchiveRestoreRollbackResult:
        """Rollback restored items using the archive restore ledger."""

        batch = await self._get_batch(restore_batch_id)
        if batch.status == RESTORE_BATCH_STATUS_IN_PROGRESS:
            recovered = await self._recover_incomplete_batch(manager=manager, batch=batch)
            if recovered is not None:
                return recovered
            batch = await self._get_batch(restore_batch_id)
        if batch.status not in {RESTORE_BATCH_STATUS_CONFIRMED, RESTORE_BATCH_STATUS_PARTIAL}:
            raise MemoryArchiveRestoreError("Archive restore batch is not eligible for rollback.")
        now = datetime.now(UTC)
        batch.status = RESTORE_BATCH_STATUS_ROLLBACK_IN_PROGRESS
        batch.rollback_status = RESTORE_BATCH_STATUS_ROLLBACK_IN_PROGRESS
        await self._db.commit()

        refs = await self._rollbacker.rollback(restore_batch_id=batch.id, manager=manager, rolled_back_at=now)
        rolled_back = _count_by_section(refs, RESTORE_ITEM_STATUS_ROLLED_BACK)
        missing_items = _count_status(refs, RESTORE_ITEM_STATUS_MISSING)
        failed_items = _count_status(refs, RESTORE_ITEM_STATUS_FAILED)
        total = sum(rolled_back.values())
        batch.rolled_back_count = total
        batch.rolled_back_at = now
        batch.status, batch.rollback_status = _rollback_batch_status(missing_items=missing_items, failed_items=failed_items)
        integrity_status: MemoryReliabilityStatus = "ready" if missing_items == 0 and failed_items == 0 else "warning"
        await self._ledger.record_event(
            kind=MemoryOperationKind.FORGET,
            status=operation_status(conflict_items=missing_items, failed_items=failed_items),
            summary="Memory archive restore rolled back.",
            source="memory_archive_restore",
            target_kind="memory_archive_restore",
            target_id=batch.id,
            correlation_id=batch.id,
            metadata={
                "restore_batch_id": batch.id,
                "rolled_back_count": total,
                "missing_items": missing_items,
                "failed_items": failed_items,
                "integrity_status": integrity_status,
            },
        )
        await self._db.commit()
        return MemoryArchiveRestoreRollbackResult(
            restore_batch_id=batch.id,
            rolled_back=rolled_back,
            total_rolled_back=total,
            missing_items=missing_items,
            failed_items=failed_items,
            integrity_status=integrity_status,
            mutation_refs=refs,
        )

    async def recover_incomplete_restores(
        self,
        manager: MemoryManager,
        *,
        include_batch_id: str | None = None,
    ) -> int:
        """Rollback interrupted restore journals before new restore work continues."""

        result = await self._db.execute(
            select(MemoryArchiveRestoreBatchModel)
            .where(MemoryArchiveRestoreBatchModel.status == RESTORE_BATCH_STATUS_IN_PROGRESS)
            .order_by(MemoryArchiveRestoreBatchModel.confirmed_at, MemoryArchiveRestoreBatchModel.id)
        )
        recovered = 0
        for batch in result.scalars().all():
            if include_batch_id is not None and batch.id != include_batch_id:
                continue
            await self._recover_incomplete_batch(manager=manager, batch=batch)
            recovered += 1
        return recovered

    async def _get_batch(self, restore_batch_id: str) -> MemoryArchiveRestoreBatchModel:
        batch = await self._db.get(MemoryArchiveRestoreBatchModel, restore_batch_id)
        if batch is None:
            raise MemoryArchiveRestoreError("Archive restore batch was not found.", status_code=404)
        return batch

    async def _recover_incomplete_batch(
        self,
        *,
        manager: MemoryManager,
        batch: MemoryArchiveRestoreBatchModel,
    ) -> MemoryArchiveRestoreRollbackResult | None:
        now = datetime.now(UTC)
        await self._rebuild_memory_ledger_from_metadata(manager=manager, batch=batch)
        items = await self._rollbacker.list_items(batch.id)
        if not items:
            batch.status = RESTORE_BATCH_STATUS_FAILED
            batch.rollback_status = RESTORE_BATCH_STATUS_FAILED
            batch.metadata_json = {
                **(batch.metadata_json or {}),
                "restore_journal": {
                    "status": RESTORE_BATCH_STATUS_FAILED,
                    "failed_at": now.isoformat(),
                    "reason": "restore_interrupted_without_ledger",
                },
            }
            await self._db.commit()
            return None
        batch.status = RESTORE_BATCH_STATUS_ROLLBACK_IN_PROGRESS
        batch.rollback_status = RESTORE_BATCH_STATUS_ROLLBACK_IN_PROGRESS
        batch.metadata_json = {
            **(batch.metadata_json or {}),
            "restore_journal": {
                "status": RESTORE_BATCH_STATUS_ROLLBACK_IN_PROGRESS,
                "started_at": now.isoformat(),
                "reason": "recover_interrupted_restore",
            },
        }
        await self._db.commit()
        refs = await self._rollbacker.rollback(restore_batch_id=batch.id, manager=manager, rolled_back_at=now)
        rolled_back = _count_by_section(refs, RESTORE_ITEM_STATUS_ROLLED_BACK)
        missing_items = _count_status(refs, RESTORE_ITEM_STATUS_MISSING)
        failed_items = _count_status(refs, RESTORE_ITEM_STATUS_FAILED)
        total = sum(rolled_back.values())
        batch = await self._get_batch(batch.id)
        batch.rolled_back_count = total
        batch.rolled_back_at = now
        batch.status, batch.rollback_status = _rollback_batch_status(missing_items=missing_items, failed_items=failed_items)
        integrity_status: MemoryReliabilityStatus = "ready" if missing_items == 0 and failed_items == 0 else "warning"
        batch.metadata_json = {
            **(batch.metadata_json or {}),
            "restore_journal": {
                "status": batch.status,
                "completed_at": datetime.now(UTC).isoformat(),
                "reason": "recover_interrupted_restore",
                "rolled_back_count": total,
                "missing_items": missing_items,
                "failed_items": failed_items,
            },
        }
        await self._db.commit()
        return MemoryArchiveRestoreRollbackResult(
            restore_batch_id=batch.id,
            rolled_back=rolled_back,
            total_rolled_back=total,
            missing_items=missing_items,
            failed_items=failed_items,
            integrity_status=integrity_status,
            mutation_refs=refs,
        )

    async def _rebuild_memory_ledger_from_metadata(
        self,
        *,
        manager: MemoryManager,
        batch: MemoryArchiveRestoreBatchModel,
    ) -> None:
        if await self._rollbacker.list_items(batch.id):
            return
        stored_refs = await manager.list_memory_refs_by_metadata("archive_restore_batch_id", batch.id)
        for memory_type, refs in stored_refs.items():
            for index, ref_data in enumerate(refs):
                memory_id = ref_data.get("id", "")
                if not memory_id:
                    continue
                source_id = ref_data.get("import_item_id") or f"{batch.id}:{memory_type}:{index}"
                ref = make_ref(
                    section="memory",
                    item_kind=f"memory.{memory_type}",
                    source_id=source_id,
                    target_id=memory_id,
                    status=RESTORE_ITEM_STATUS_RESTORED,
                    reason="recovered_from_restore_metadata",
                )
                self._db.add(
                    add_restore_item(
                        batch_id=batch.id,
                        ref=ref,
                        metadata={
                            "memory_type": memory_type,
                            "memory_ids": [memory_id],
                            "recovered_from_restore_metadata": True,
                        },
                    )
                )
        await self._db.flush()

    async def _mark_restore_apply_failed(self, batch_id: str, exc: Exception) -> None:
        await self._db.rollback()
        batch = await self._get_batch(batch_id)
        now = datetime.now(UTC)
        batch.status = RESTORE_BATCH_STATUS_FAILED
        batch.failed_count = max(batch.failed_count, 1)
        batch.rollback_status = RESTORE_BATCH_STATUS_FAILED
        batch.metadata_json = {
            **(batch.metadata_json or {}),
            "restore_journal": {
                "status": RESTORE_BATCH_STATUS_FAILED,
                "failed_at": now.isoformat(),
                "error_type": exc.__class__.__name__,
                "error": str(exc),
            },
        }
        await self._db.commit()


def _count_by_section(refs: object, status: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    if not isinstance(refs, list):
        return counts
    for ref in refs:
        if getattr(ref, "status", "") == status:
            section = str(getattr(ref, "section", ""))
            counts[section] = counts.get(section, 0) + 1
    return counts


def _count_status(refs: object, status: str) -> int:
    if not isinstance(refs, list):
        return 0
    return sum(1 for ref in refs if getattr(ref, "status", "") == status)


def _validate_review_hashes(
    *,
    preview: MemoryArchiveRestoreDryRunResult,
    expected_payload_hash: str,
    expected_plan_hash: str,
) -> None:
    if not expected_payload_hash or preview.payload_hash != expected_payload_hash:
        raise MemoryArchiveRestoreError("Archive restore payload hash does not match the reviewed dry-run.", status_code=409)
    if not expected_plan_hash or preview.plan.plan_hash != expected_plan_hash:
        raise MemoryArchiveRestoreError("Archive restore plan hash does not match the reviewed dry-run.", status_code=409)


def _restore_batch_status(*, total_restored: int, failed_items: int) -> str:
    if failed_items <= 0:
        return "confirmed"
    return "partial" if total_restored > 0 else "failed"


def _rollback_batch_status(*, missing_items: int, failed_items: int) -> tuple[str, str]:
    if failed_items > 0:
        return RESTORE_BATCH_STATUS_ROLLBACK_FAILED, RESTORE_BATCH_STATUS_ROLLBACK_FAILED
    if missing_items > 0:
        return RESTORE_BATCH_STATUS_PARTIAL, RESTORE_BATCH_STATUS_PARTIAL
    return RESTORE_BATCH_STATUS_ROLLED_BACK, RESTORE_BATCH_STATUS_ROLLED_BACK
