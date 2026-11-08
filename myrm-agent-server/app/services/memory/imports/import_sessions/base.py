"""[INPUT]
- app.services.memory.imports.* 与 database/schemas（POS: 导入会话依赖）

[OUTPUT]
- MemoryImportSessionError / ImportReadinessRecheckFacts / 常量与纯函数
- MemoryImportSessionBase: 共享 db 会话与跨阶段方法声明

[POS]
`app/services/memory/imports/import_sessions/` 的共享类型与状态。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.memory import MemoryImportBatchModel, MemoryImportDryRunModel
from app.services.memory.imports.import_ledger import (
    IMPORT_BATCH_STATUS_ROLLBACK_IN_PROGRESS,
    MemoryImportLedgerService,
)
from app.services.memory.ledger.operation_ledger import MemoryOperationLedgerService

DRY_RUN_TTL_SECONDS = 30 * 60
DRY_RUN_RETENTION_DAYS = 7
DRY_RUN_STATUS_PENDING = "pending"
DRY_RUN_STATUS_CONFIRMED = "confirmed"
DRY_RUN_STATUS_EXPIRED = "expired"
DRY_RUN_STATUS_ROLLED_BACK = "rolled_back"


class MemoryImportSessionError(Exception):
    """Raised when an import review session cannot be confirmed."""

    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class ImportReadinessRecheckFacts:
    """Stored import-batch facts combined with live provider checks during recheck."""

    source_has_api_keys: bool
    diagnostic_status: str | None
    diagnostic_failed_count: int
    mcp_config_count: int
    workspace_rules_skipped: int
    migration_competitor: str | None = None

    def to_metadata_block(self) -> dict[str, object]:
        block: dict[str, object] = {
            "source_has_api_keys": self.source_has_api_keys,
            "diagnostic_status": self.diagnostic_status,
            "diagnostic_failed_count": self.diagnostic_failed_count,
            "mcp_config_count": self.mcp_config_count,
            "workspace_rules_skipped": self.workspace_rules_skipped,
        }
        if self.migration_competitor:
            block["migration_competitor"] = self.migration_competitor
        return block

    @classmethod
    def from_metadata_block(cls, block: dict[str, object]) -> ImportReadinessRecheckFacts:
        diagnostic_status_raw = block.get("diagnostic_status")
        diagnostic_status = (
            diagnostic_status_raw.strip() if isinstance(diagnostic_status_raw, str) and diagnostic_status_raw.strip() else None
        )
        competitor_raw = block.get("migration_competitor")
        migration_competitor = competitor_raw.strip() if isinstance(competitor_raw, str) and competitor_raw.strip() else None
        return cls(
            source_has_api_keys=block.get("source_has_api_keys") is True,
            diagnostic_status=diagnostic_status,
            diagnostic_failed_count=_coerce_non_negative_int(block.get("diagnostic_failed_count")),
            mcp_config_count=_coerce_non_negative_int(block.get("mcp_config_count")),
            workspace_rules_skipped=_coerce_non_negative_int(block.get("workspace_rules_skipped")),
            migration_competitor=migration_competitor,
        )


def _coerce_non_negative_int(value: object) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return max(0, value)
    if isinstance(value, float):
        return max(0, int(value))
    return 0


def _as_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def _rollback_in_progress(batch: MemoryImportBatchModel) -> bool:
    return (
        batch.status == IMPORT_BATCH_STATUS_ROLLBACK_IN_PROGRESS
        or batch.rollback_status == IMPORT_BATCH_STATUS_ROLLBACK_IN_PROGRESS
    )


class MemoryImportSessionBase:
    """Shared db session and ledger services; concrete methods live in sibling mixins."""

    _db: AsyncSession
    _ledger: MemoryOperationLedgerService
    _import_ledger: MemoryImportLedgerService

    async def _expire_stale(self) -> None:
        raise NotImplementedError

    async def cleanup_sessions(self, *, retention_days: int = DRY_RUN_RETENTION_DAYS) -> int:
        raise NotImplementedError

    async def _get_pending_row(self, dry_run_id: str) -> MemoryImportDryRunModel:
        raise NotImplementedError

    async def _get_confirmed_batch(
        self,
        *,
        dry_run_id: str | None,
        import_batch_id: str | None,
    ) -> MemoryImportBatchModel:
        raise NotImplementedError

    async def _get_rollback_batch(
        self,
        *,
        dry_run_id: str | None,
        import_batch_id: str | None,
    ) -> MemoryImportBatchModel:
        raise NotImplementedError
