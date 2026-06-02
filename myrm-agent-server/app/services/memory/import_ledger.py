"""Memory import transaction ledger service.

[INPUT]
app.database.models.memory::MemoryImportBatchModel, MemoryImportItemModel (POS: 导入批次和条目账本)

[OUTPUT]
MemoryImportLedgerService: durable import batch/item state machine for rollback and audit.

[POS]
把导入确认后的回滚事实从 dry-run JSON 中剥离为关系型账本。账本只保存 memory id、类型、画像键和值指纹等必要数据，不保存导入正文。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.memory import MemoryImportBatchModel, MemoryImportItemModel

IMPORT_BATCH_STATUS_CONFIRMED = "confirmed"
IMPORT_BATCH_STATUS_ROLLBACK_IN_PROGRESS = "rollback_in_progress"
IMPORT_BATCH_STATUS_ROLLED_BACK = "rolled_back"
IMPORT_BATCH_STATUS_PARTIAL = "partial"
IMPORT_BATCH_STATUS_ROLLBACK_FAILED = "rollback_failed"

IMPORT_ITEM_STATUS_IMPORTED = "imported"
IMPORT_ITEM_STATUS_SKIPPED = "skipped"
IMPORT_ITEM_STATUS_ROLLED_BACK = "rolled_back"
IMPORT_ITEM_STATUS_CONFLICT = "conflict"
IMPORT_ITEM_STATUS_MISSING = "missing"
IMPORT_ITEM_STATUS_ROLLBACK_FAILED = "rollback_failed"

ROLLBACK_WARNING_NO_REVERSIBLE_ITEMS = "no_reversible_items"
ROLLBACK_WARNING_PROFILE_CONFLICTS = "profile_conflicts"
ROLLBACK_WARNING_PROFILE_GUARDED = "profile_guarded"
ROLLBACK_WARNING_MEMORY_ROWS_MISSING = "memory_rows_missing"

ImportRollbackHealthStatus = Literal["ready", "warning", "critical"]


@dataclass(frozen=True)
class ImportRollbackWarning:
    """Structured rollback warning for API/UI translation."""

    code: str
    severity: str
    params: dict[str, str | int | float | bool]


@dataclass(frozen=True)
class ImportRollbackHealth:
    """Content-free import rollback health counters."""

    in_progress_batches: int = 0
    failed_batches: int = 0
    partial_batches: int = 0
    missing_items: int = 0
    failed_items: int = 0

    @property
    def status(self) -> ImportRollbackHealthStatus:
        if self.failed_batches > 0 or self.failed_items > 0:
            return "critical"
        if self.in_progress_batches > 0 or self.partial_batches > 0 or self.missing_items > 0:
            return "warning"
        return "ready"


class MemoryImportLedgerService:
    """Persists confirmed import batches and item-level rollback state."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def record_confirmed_batch(
        self,
        *,
        import_batch_id: str,
        dry_run_id: str,
        source: str,
        payload_hash: str,
        imported_count: int,
        unmapped_count: int,
        transaction_items: list[dict[str, object]],
        metadata: dict[str, object] | None = None,
    ) -> MemoryImportBatchModel:
        now = datetime.now(UTC)
        batch = MemoryImportBatchModel(
            id=import_batch_id,
            dry_run_id=dry_run_id,
            source=source,
            status=IMPORT_BATCH_STATUS_CONFIRMED,
            payload_hash=payload_hash,
            imported_count=imported_count,
            unmapped_count=unmapped_count,
            transaction_item_count=len(transaction_items),
            created_at=now,
            confirmed_at=now,
            metadata_json=metadata,
        )
        self._db.add(batch)
        for item in transaction_items:
            self._db.add(_transaction_item_to_row(import_batch_id, item, now))
        return batch

    async def merge_batch_metadata(
        self,
        import_batch_id: str,
        patch: dict[str, object],
    ) -> None:
        """Merge keys into a confirmed import batch metadata document."""

        batch = await self._db.get(MemoryImportBatchModel, import_batch_id)
        if batch is None:
            return
        current = batch.metadata_json if isinstance(batch.metadata_json, dict) else {}
        batch.metadata_json = {**current, **patch}
        await self._db.commit()

    async def get_batch(
        self,
        *,
        dry_run_id: str | None,
        import_batch_id: str | None,
    ) -> MemoryImportBatchModel | None:
        if dry_run_id:
            result = await self._db.execute(
                select(MemoryImportBatchModel)
                .where(MemoryImportBatchModel.dry_run_id == dry_run_id)
                .order_by(desc(MemoryImportBatchModel.confirmed_at))
                .limit(1)
            )
            return result.scalar_one_or_none()
        if import_batch_id:
            return await self._db.get(MemoryImportBatchModel, import_batch_id)
        return None

    async def list_items(self, batch_id: str) -> list[MemoryImportItemModel]:
        result = await self._db.execute(
            select(MemoryImportItemModel)
            .where(MemoryImportItemModel.batch_id == batch_id)
            .order_by(MemoryImportItemModel.created_at, MemoryImportItemModel.id)
        )
        return list(result.scalars().all())

    async def list_incomplete_rollbacks(self) -> list[MemoryImportBatchModel]:
        result = await self._db.execute(
            select(MemoryImportBatchModel)
            .where(MemoryImportBatchModel.rollback_status == IMPORT_BATCH_STATUS_ROLLBACK_IN_PROGRESS)
            .order_by(MemoryImportBatchModel.confirmed_at)
        )
        return list(result.scalars().all())

    async def rollback_health(self) -> ImportRollbackHealth:
        """Return content-free rollback journal and item health counters."""

        batch_result = await self._db.execute(
            select(MemoryImportBatchModel.status, func.count())
            .where(
                MemoryImportBatchModel.status.in_(
                    [
                        IMPORT_BATCH_STATUS_ROLLBACK_IN_PROGRESS,
                        IMPORT_BATCH_STATUS_ROLLBACK_FAILED,
                        IMPORT_BATCH_STATUS_PARTIAL,
                    ]
                )
            )
            .group_by(MemoryImportBatchModel.status)
        )
        batch_counts = {str(status): int(count) for status, count in batch_result.all()}
        item_result = await self._db.execute(
            select(MemoryImportItemModel.status, func.count())
            .where(MemoryImportItemModel.status.in_([IMPORT_ITEM_STATUS_MISSING, IMPORT_ITEM_STATUS_ROLLBACK_FAILED]))
            .group_by(MemoryImportItemModel.status)
        )
        item_counts = {str(status): int(count) for status, count in item_result.all()}
        return ImportRollbackHealth(
            in_progress_batches=batch_counts.get(IMPORT_BATCH_STATUS_ROLLBACK_IN_PROGRESS, 0),
            failed_batches=batch_counts.get(IMPORT_BATCH_STATUS_ROLLBACK_FAILED, 0),
            partial_batches=batch_counts.get(IMPORT_BATCH_STATUS_PARTIAL, 0),
            missing_items=item_counts.get(IMPORT_ITEM_STATUS_MISSING, 0),
            failed_items=item_counts.get(IMPORT_ITEM_STATUS_ROLLBACK_FAILED, 0),
        )

    def begin_batch_rollback(self, batch: MemoryImportBatchModel, *, started_at: datetime) -> None:
        batch.status = IMPORT_BATCH_STATUS_ROLLBACK_IN_PROGRESS
        batch.rollback_status = IMPORT_BATCH_STATUS_ROLLBACK_IN_PROGRESS
        batch.metadata_json = {
            **(batch.metadata_json or {}),
            "rollback_journal": {
                "status": IMPORT_BATCH_STATUS_ROLLBACK_IN_PROGRESS,
                "started_at": started_at.isoformat(),
            },
        }

    async def save_post_import_diagnostic(
        self,
        *,
        import_batch_id: str,
        diagnostic_run_id: str,
        diagnostic_status: str,
        failed_count: int,
    ) -> None:
        batch = await self._db.get(MemoryImportBatchModel, import_batch_id)
        if batch is None:
            return
        batch.diagnostic_run_id = diagnostic_run_id
        batch.diagnostic_status = diagnostic_status
        batch.diagnostic_failed_count = failed_count

    def mark_item_rolled_back(self, item: MemoryImportItemModel, *, rolled_back_at: datetime) -> None:
        item.status = IMPORT_ITEM_STATUS_ROLLED_BACK
        item.rollback_status = IMPORT_ITEM_STATUS_ROLLED_BACK
        item.rollback_error = None
        item.rolled_back_at = rolled_back_at

    def mark_item_conflict(self, item: MemoryImportItemModel, *, reason: str, rolled_back_at: datetime) -> None:
        item.status = IMPORT_ITEM_STATUS_CONFLICT
        item.rollback_status = IMPORT_ITEM_STATUS_CONFLICT
        item.rollback_error = reason
        item.rolled_back_at = rolled_back_at

    def mark_item_missing(self, item: MemoryImportItemModel, *, reason: str, rolled_back_at: datetime) -> None:
        item.status = IMPORT_ITEM_STATUS_MISSING
        item.rollback_status = IMPORT_ITEM_STATUS_MISSING
        item.rollback_error = reason
        item.rolled_back_at = rolled_back_at

    def mark_item_failed(self, item: MemoryImportItemModel, *, reason: str, rolled_back_at: datetime) -> None:
        item.status = IMPORT_ITEM_STATUS_ROLLBACK_FAILED
        item.rollback_status = IMPORT_ITEM_STATUS_ROLLBACK_FAILED
        item.rollback_error = reason
        item.rolled_back_at = rolled_back_at

    def mark_batch_rollback(
        self,
        batch: MemoryImportBatchModel,
        *,
        rolled_back_count: int,
        conflict_count: int,
        missing_count: int,
        failed_count: int,
        rolled_back_at: datetime,
    ) -> None:
        if failed_count > 0:
            status = IMPORT_BATCH_STATUS_ROLLBACK_FAILED
        elif conflict_count > 0 or missing_count > 0:
            status = IMPORT_BATCH_STATUS_PARTIAL
        else:
            status = IMPORT_BATCH_STATUS_ROLLED_BACK
        batch.status = status
        batch.rollback_status = status
        batch.rolled_back_count = rolled_back_count
        batch.rolled_back_at = rolled_back_at


def _transaction_item_to_row(
    batch_id: str,
    item: dict[str, object],
    created_at: datetime,
) -> MemoryImportItemModel:
    raw_item_id = item.get("item_id")
    if not isinstance(raw_item_id, str) or not raw_item_id:
        raise ValueError("Import transaction item is missing item_id.")
    raw_type = item.get("memory_type")
    if not isinstance(raw_type, str) or not raw_type:
        raise ValueError("Import transaction item is missing memory_type.")
    raw_status = item.get("status")
    status = raw_status if isinstance(raw_status, str) and raw_status else IMPORT_ITEM_STATUS_SKIPPED
    memory_ids = _string_list(item.get("memory_ids"))
    profile_key = item.get("profile_key")
    profile_previous_value = item.get("profile_previous_value")
    profile_imported_value = item.get("profile_imported_value")
    profile_previous_revision = item.get("profile_previous_revision")
    profile_imported_revision = item.get("profile_imported_revision")
    return MemoryImportItemModel(
        id=raw_item_id,
        batch_id=batch_id,
        memory_type=raw_type,
        status=status,
        memory_ids_json=memory_ids,
        profile_key=profile_key if isinstance(profile_key, str) and profile_key else None,
        profile_previous_value=profile_previous_value if isinstance(profile_previous_value, str) else None,
        profile_imported_value=profile_imported_value if isinstance(profile_imported_value, str) else None,
        profile_previous_revision=profile_previous_revision if isinstance(profile_previous_revision, str) else None,
        profile_imported_revision=profile_imported_revision if isinstance(profile_imported_revision, str) else None,
        profile_previous_value_present=bool(item.get("profile_previous_value_present")),
        profile_imported_value_present=bool(item.get("profile_imported_value_present")),
        created_at=created_at,
        metadata_json=_object_dict(item.get("metadata")),
    )


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _object_dict(value: object) -> dict[str, object] | None:
    if not isinstance(value, dict):
        return None
    return {str(key): item for key, item in value.items()}
