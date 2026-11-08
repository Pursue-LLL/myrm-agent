"""[INPUT]
- .base (POS: 共享类型、常量与状态)

[OUTPUT]
- ImportQueriesMixin: 批次/会话查询、清理与指标

[POS]
`import_sessions/` 的查询阶段；只读/过期清理，不改变导入语义。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select, update

from app.database.models.memory import MemoryImportBatchModel, MemoryImportDryRunModel
from app.services.memory.imports.import_ledger import (
    IMPORT_BATCH_STATUS_CONFIRMED,
)

from .base import (
    DRY_RUN_RETENTION_DAYS,
    DRY_RUN_STATUS_CONFIRMED,
    DRY_RUN_STATUS_EXPIRED,
    DRY_RUN_STATUS_PENDING,
    DRY_RUN_STATUS_ROLLED_BACK,
    MemoryImportSessionBase,
    MemoryImportSessionError,
    _as_aware,
    _rollback_in_progress,
)


class ImportQueriesMixin(MemoryImportSessionBase):
    """批次/会话查询、清理与指标。"""

    async def cleanup_sessions(self, *, retention_days: int = DRY_RUN_RETENTION_DAYS) -> int:
        """Remove completed import review sessions after the rollback retention window."""

        cutoff = datetime.now(UTC) - timedelta(days=retention_days)
        result = await self._db.execute(
            delete(MemoryImportDryRunModel)
            .where(MemoryImportDryRunModel.status != DRY_RUN_STATUS_PENDING)
            .where(MemoryImportDryRunModel.created_at < cutoff)
        )
        await self._db.commit()
        return int(result.rowcount or 0)


    async def session_metrics(self) -> dict[str, int]:
        """Return content-free import review session counts for maintenance visibility."""

        metrics: dict[str, int] = {
            DRY_RUN_STATUS_PENDING: 0,
            DRY_RUN_STATUS_CONFIRMED: 0,
            DRY_RUN_STATUS_EXPIRED: 0,
            DRY_RUN_STATUS_ROLLED_BACK: 0,
        }
        now = datetime.now(UTC)
        result = await self._db.execute(select(MemoryImportDryRunModel.status, MemoryImportDryRunModel.expires_at))
        for status, expires_at in result.all():
            effective_status = (
                DRY_RUN_STATUS_EXPIRED if status == DRY_RUN_STATUS_PENDING and _as_aware(expires_at) <= now else str(status)
            )
            metrics[effective_status] = metrics.get(effective_status, 0) + 1
        return metrics


    async def get_pending_session_metadata(self, dry_run_id: str) -> dict[str, object]:
        """Return metadata stored on a pending dry-run session (e.g. migration instruction plan)."""

        row = await self._get_pending_row(dry_run_id)
        raw = row.metadata_json
        return raw if isinstance(raw, dict) else {}


    async def _get_pending_row(self, dry_run_id: str) -> MemoryImportDryRunModel:
        row = await self._db.get(MemoryImportDryRunModel, dry_run_id)
        if row is None:
            raise MemoryImportSessionError("Import review session was not found.", status_code=404)
        if row.status != DRY_RUN_STATUS_PENDING:
            raise MemoryImportSessionError("Import review session is no longer pending.")
        if _as_aware(row.expires_at) <= datetime.now(UTC):
            row.status = DRY_RUN_STATUS_EXPIRED
            await self._db.commit()
            raise MemoryImportSessionError("Import review session has expired.")
        return row


    async def _get_confirmed_batch(
        self,
        *,
        dry_run_id: str | None,
        import_batch_id: str | None,
    ) -> MemoryImportBatchModel:
        batch = await self._get_batch(dry_run_id=dry_run_id, import_batch_id=import_batch_id)
        if batch.status != IMPORT_BATCH_STATUS_CONFIRMED:
            raise MemoryImportSessionError("Import batch is not eligible for rollback.")
        return batch


    async def _get_rollback_batch(
        self,
        *,
        dry_run_id: str | None,
        import_batch_id: str | None,
    ) -> MemoryImportBatchModel:
        batch = await self._get_batch(dry_run_id=dry_run_id, import_batch_id=import_batch_id)
        if batch.status != IMPORT_BATCH_STATUS_CONFIRMED and not _rollback_in_progress(batch):
            raise MemoryImportSessionError("Import batch is not eligible for rollback.")
        return batch


    async def _get_batch(
        self,
        *,
        dry_run_id: str | None,
        import_batch_id: str | None,
    ) -> MemoryImportBatchModel:
        if not dry_run_id and not import_batch_id:
            raise MemoryImportSessionError("Rollback requires a dry-run id or import batch id.")
        if dry_run_id and import_batch_id:
            raise MemoryImportSessionError("Rollback accepts either dry-run id or import batch id, not both.")
        batch = await self._import_ledger.get_batch(dry_run_id=dry_run_id, import_batch_id=import_batch_id)
        if batch is None:
            raise MemoryImportSessionError("Import batch was not found.", status_code=404)
        return batch


    async def _expire_stale(self) -> None:
        await self._db.execute(
            update(MemoryImportDryRunModel)
            .where(MemoryImportDryRunModel.status == DRY_RUN_STATUS_PENDING)
            .where(MemoryImportDryRunModel.expires_at <= datetime.now(UTC))
            .values(status=DRY_RUN_STATUS_EXPIRED)
        )
        await self._db.commit()
