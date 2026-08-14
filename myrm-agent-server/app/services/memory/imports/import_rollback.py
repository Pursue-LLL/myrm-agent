"""Memory import rollback helpers.

[INPUT]
app.database.models.memory::MemoryImportItemModel (POS: 记忆域模型),
app.services.memory.import_ledger::MemoryImportLedgerService (POS: 导入批次/条目账本状态机),
myrm_agent_harness.toolkits.memory::MemoryManager (POS: Unified memory manager and core facade of the Memory Toolkit)

[OUTPUT]
count_profile_conflicts, preview_items_by_type, rollback_preview_warnings,
rollback_memory_items, rollback_profile_items: content-safe import rollback planning and execution helpers.

[POS]
记忆导入回滚辅助层。封装账本条目分类、画像并发冲突检测、结构化告警生成和按 type/id 精准回滚执行。
"""

from __future__ import annotations

from datetime import datetime

from myrm_agent_harness.toolkits.memory import MemoryManager, MemoryType

from app.database.models.memory import MemoryImportItemModel
from app.services.memory.import_ledger import (
    IMPORT_ITEM_STATUS_IMPORTED,
    ROLLBACK_WARNING_MEMORY_ROWS_MISSING,
    ROLLBACK_WARNING_NO_REVERSIBLE_ITEMS,
    ROLLBACK_WARNING_PROFILE_CONFLICTS,
    ROLLBACK_WARNING_PROFILE_GUARDED,
    ImportRollbackWarning,
    MemoryImportLedgerService,
)


class ProfileRollbackResult:
    """Profile rollback aggregate result."""

    def __init__(self, *, rolled_back: int, conflicts: int) -> None:
        self.rolled_back = rolled_back
        self.conflicts = conflicts


class MemoryRollbackResult:
    """Memory rollback aggregate result."""

    def __init__(
        self,
        *,
        rolled_back: dict[str, int],
        deleted_refs: list[dict[str, str]],
        missing_refs: list[dict[str, str]],
        forbidden_refs: list[dict[str, str]],
        failed_refs: list[dict[str, str]],
    ) -> None:
        self.rolled_back = rolled_back
        self.deleted_refs = deleted_refs
        self.missing_refs = missing_refs
        self.forbidden_refs = forbidden_refs
        self.failed_refs = failed_refs


def is_imported_profile_item(item: MemoryImportItemModel) -> bool:
    return item.memory_type == MemoryType.PROFILE.value and item.status == IMPORT_ITEM_STATUS_IMPORTED


def is_imported_memory_item(item: MemoryImportItemModel) -> bool:
    return item.memory_type != MemoryType.PROFILE.value and item.status == IMPORT_ITEM_STATUS_IMPORTED


async def count_profile_conflicts(manager: MemoryManager, items: list[MemoryImportItemModel]) -> int:
    conflicts = 0
    for item in items:
        if item.profile_key and not await profile_matches_imported(manager, item):
            conflicts += 1
    return conflicts


def preview_items_by_type(
    items: list[MemoryImportItemModel],
    *,
    profile_conflicts: int,
) -> dict[str, int]:
    counts: dict[str, int] = {}
    imported_profile_count = 0
    for item in items:
        if item.status != IMPORT_ITEM_STATUS_IMPORTED:
            continue
        if item.memory_type == MemoryType.PROFILE.value:
            if item.profile_key:
                imported_profile_count += 1
            continue
        counts[item.memory_type] = counts.get(item.memory_type, 0) + len(item.memory_ids_json)
    reversible_profiles = max(imported_profile_count - profile_conflicts, 0)
    if reversible_profiles:
        counts[MemoryType.PROFILE.value] = reversible_profiles
    return {memory_type: count for memory_type, count in counts.items() if count > 0}


def rollback_preview_warnings(
    *,
    reversible_items: int,
    profile_keys: list[str],
    profile_conflicts: int,
    memory_rows_missing: int,
) -> list[ImportRollbackWarning]:
    warnings: list[ImportRollbackWarning] = []
    if reversible_items == 0:
        warnings.append(
            ImportRollbackWarning(
                code=ROLLBACK_WARNING_NO_REVERSIBLE_ITEMS,
                severity="warning",
                params={},
            )
        )
    if profile_keys:
        warnings.append(
            ImportRollbackWarning(
                code=ROLLBACK_WARNING_PROFILE_GUARDED,
                severity="info",
                params={"count": len(profile_keys)},
            )
        )
    if profile_conflicts:
        warnings.append(
            ImportRollbackWarning(
                code=ROLLBACK_WARNING_PROFILE_CONFLICTS,
                severity="warning",
                params={"count": profile_conflicts},
            )
        )
    if memory_rows_missing:
        warnings.append(
            ImportRollbackWarning(
                code=ROLLBACK_WARNING_MEMORY_ROWS_MISSING,
                severity="warning",
                params={"count": memory_rows_missing},
            )
        )
    return warnings


async def rollback_memory_items(
    manager: MemoryManager,
    ledger: MemoryImportLedgerService,
    items: list[MemoryImportItemModel],
    *,
    rolled_back_at: datetime,
) -> MemoryRollbackResult:
    ids_by_type: dict[str, list[str]] = {}
    rollback_items: list[MemoryImportItemModel] = []
    for item in items:
        if not is_imported_memory_item(item):
            continue
        rollback_items.append(item)
        ids_by_type.setdefault(item.memory_type, []).extend(item.memory_ids_json)
    mutation_result = await manager.delete_memories_by_ids(ids_by_type)
    deleted_refs = _ref_keys(mutation_result.deleted_refs)
    missing_refs = _ref_keys(mutation_result.missing_refs)
    forbidden_refs = _ref_keys(mutation_result.forbidden_refs)
    failed_refs = _ref_keys(mutation_result.failed_refs)
    for item in rollback_items:
        item_refs = {(item.memory_type, memory_id) for memory_id in item.memory_ids_json}
        if item_refs and item_refs.issubset(deleted_refs):
            ledger.mark_item_rolled_back(item, rolled_back_at=rolled_back_at)
        elif item_refs & (forbidden_refs | failed_refs):
            ledger.mark_item_failed(item, reason="memory row deletion failed", rolled_back_at=rolled_back_at)
        elif item_refs & missing_refs:
            ledger.mark_item_missing(item, reason="memory row was already missing", rolled_back_at=rolled_back_at)
        else:
            ledger.mark_item_failed(item, reason="memory row was not deleted", rolled_back_at=rolled_back_at)
    return MemoryRollbackResult(
        rolled_back=mutation_result.deleted_counts_by_type(),
        deleted_refs=_ref_dicts(mutation_result.deleted_refs),
        missing_refs=_ref_dicts(mutation_result.missing_refs),
        forbidden_refs=_ref_dicts(mutation_result.forbidden_refs),
        failed_refs=_ref_dicts(mutation_result.failed_refs),
    )


async def rollback_profile_items(
    manager: MemoryManager,
    ledger: MemoryImportLedgerService,
    items: list[MemoryImportItemModel],
    *,
    rolled_back_at: datetime,
) -> ProfileRollbackResult:
    rolled_back = 0
    conflicts = 0
    for item in items:
        if not is_imported_profile_item(item) or not item.profile_key:
            continue
        if not await profile_matches_imported(manager, item):
            ledger.mark_item_conflict(item, reason="profile value changed after import", rolled_back_at=rolled_back_at)
            conflicts += 1
            continue
        restore_value = item.profile_previous_value if item.profile_previous_value_present else None
        rolled_back += await manager.restore_profile_attributes({item.profile_key: restore_value})
        ledger.mark_item_rolled_back(item, rolled_back_at=rolled_back_at)
    return ProfileRollbackResult(rolled_back=rolled_back, conflicts=conflicts)


async def profile_matches_imported(manager: MemoryManager, item: MemoryImportItemModel) -> bool:
    if not item.profile_key:
        return False
    current_snapshot = await manager.get_profile_attribute_snapshot(item.profile_key)
    if item.profile_imported_revision:
        return current_snapshot.exists and current_snapshot.revision == item.profile_imported_revision
    if not item.profile_imported_value_present:
        return not current_snapshot.exists
    return current_snapshot.value == item.profile_imported_value


def _ref_keys(refs: object) -> set[tuple[str, str]]:
    keys: set[tuple[str, str]] = set()
    if not isinstance(refs, list):
        return keys
    for ref in refs:
        memory_type = getattr(ref, "memory_type", None)
        memory_id = getattr(ref, "memory_id", None)
        if isinstance(memory_type, str) and isinstance(memory_id, str):
            keys.add((memory_type, memory_id))
    return keys


def _ref_dicts(refs: object) -> list[dict[str, str]]:
    values: list[dict[str, str]] = []
    if not isinstance(refs, list):
        return values
    for ref in refs:
        memory_type = getattr(ref, "memory_type", None)
        memory_id = getattr(ref, "memory_id", None)
        backend = getattr(ref, "backend", None)
        reason = getattr(ref, "reason", None)
        if isinstance(memory_type, str) and isinstance(memory_id, str):
            values.append(
                {
                    "memory_type": memory_type,
                    "memory_id": memory_id,
                    "backend": backend if isinstance(backend, str) else "",
                    "reason": reason if isinstance(reason, str) else "",
                }
            )
    return values
