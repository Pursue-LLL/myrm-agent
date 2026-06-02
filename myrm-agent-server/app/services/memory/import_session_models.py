"""Memory import session DTOs.

[INPUT]
app.services.memory.import_ledger::ImportRollbackWarning (POS: 导入批次/条目账本状态机)

[OUTPUT]
NormalizedMemoryData, MemoryImportConfirmResult, MemoryImportRollbackResult,
MemoryImportRollbackPreviewResult: service-layer import session DTOs.

[POS]
记忆导入会话 DTO 层。集中定义导入确认、回滚预演和回滚执行的服务层返回对象。
"""

from __future__ import annotations

from app.services.memory.import_ledger import ImportRollbackWarning

NormalizedMemoryData = dict[str, list[dict[str, object]]]


class MemoryImportConfirmResult:
    """Bound import confirmation result."""

    def __init__(
        self,
        *,
        imported: dict[str, int],
        total_imported: int,
        import_batch_id: str,
        payload_hash: str,
        source: str,
        transaction_items: list[dict[str, object]],
        diagnostic_status: str | None = None,
        diagnostic_run_id: str | None = None,
    ) -> None:
        self.imported = imported
        self.total_imported = total_imported
        self.import_batch_id = import_batch_id
        self.payload_hash = payload_hash
        self.source = source
        self.transaction_items = transaction_items
        self.diagnostic_status = diagnostic_status
        self.diagnostic_run_id = diagnostic_run_id


class MemoryImportRollbackResult:
    """Bound import rollback result."""

    def __init__(
        self,
        *,
        import_batch_id: str,
        rolled_back: dict[str, int],
        total_rolled_back: int,
        source: str,
        conflict_items: int = 0,
        missing_items: int = 0,
        failed_items: int = 0,
        deleted_refs: list[dict[str, str]] | None = None,
        missing_refs: list[dict[str, str]] | None = None,
        forbidden_refs: list[dict[str, str]] | None = None,
        failed_refs: list[dict[str, str]] | None = None,
        integrity_status: str = "not_checked",
    ) -> None:
        self.import_batch_id = import_batch_id
        self.rolled_back = rolled_back
        self.total_rolled_back = total_rolled_back
        self.source = source
        self.conflict_items = conflict_items
        self.missing_items = missing_items
        self.failed_items = failed_items
        self.deleted_refs = deleted_refs or []
        self.missing_refs = missing_refs or []
        self.forbidden_refs = forbidden_refs or []
        self.failed_refs = failed_refs or []
        self.integrity_status = integrity_status


class MemoryImportRollbackPreviewResult:
    """Content-safe rollback preview for a confirmed import batch."""

    def __init__(
        self,
        *,
        import_batch_id: str,
        source: str,
        total_items: int,
        reversible_items: int,
        items_by_type: dict[str, int],
        profile_keys: list[str],
        warnings: list[ImportRollbackWarning],
        skipped_items: int = 0,
        conflict_items: int = 0,
        missing_items: int = 0,
    ) -> None:
        self.import_batch_id = import_batch_id
        self.source = source
        self.total_items = total_items
        self.reversible_items = reversible_items
        self.items_by_type = items_by_type
        self.profile_keys = profile_keys
        self.warnings = warnings
        self.skipped_items = skipped_items
        self.conflict_items = conflict_items
        self.missing_items = missing_items
