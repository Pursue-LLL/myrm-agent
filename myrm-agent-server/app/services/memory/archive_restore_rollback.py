"""Memory Archive restore rollback helpers.

[INPUT]
app.database.models.memory::MemoryArchiveRestoreBatchModel (POS: 记忆域 ORM 模型)
myrm_agent_harness.toolkits.memory::MemoryManager (POS: framework archive DTOs)

[OUTPUT]
Rollback preview and rollback mutation refs.

[POS]
归档恢复回滚执行层。按恢复账本精准撤销 memory、Shared Context、conversation、replay 和 audit 写入。
"""

from __future__ import annotations

from datetime import datetime

from myrm_agent_harness.toolkits.memory import (
    MemoryArchiveRestoreMutationRef,
    MemoryArchiveRestoreRollbackPreview,
    MemoryManager,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.agent_event import AgentTurn
from app.database.models.chat import Chat
from app.database.models.memory import (
    MemoryArchiveRestoreItemModel,
    MemoryOperationEventModel,
    SharedContextBindingModel,
    SharedContextModel,
    SharedContextWriteProposalModel,
)
from app.services.memory.archive_restore_common import (
    RESTORE_ITEM_STATUS_CONFLICT,
    RESTORE_ITEM_STATUS_FAILED,
    RESTORE_ITEM_STATUS_MISSING,
    RESTORE_ITEM_STATUS_RESTORED,
    RESTORE_ITEM_STATUS_ROLLED_BACK,
    item_to_ref,
    mark_restore_item,
    object_dict,
)


class MemoryArchiveRestoreRollbacker:
    """Previews and executes rollback for archive restore ledger items."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def preview(self, restore_batch_id: str) -> MemoryArchiveRestoreRollbackPreview:
        items = await self.list_items(restore_batch_id)
        reversible = [item for item in items if item.status == RESTORE_ITEM_STATUS_RESTORED]
        items_by_section: dict[str, int] = {}
        missing_items = 0
        for item in reversible:
            if await self._target_exists(item):
                items_by_section[item.section] = items_by_section.get(item.section, 0) + 1
            else:
                missing_items += 1
        warning_codes = ["no_reversible_items"] if not items_by_section else []
        if missing_items:
            warning_codes.append("restore_targets_missing")
        return MemoryArchiveRestoreRollbackPreview(
            restore_batch_id=restore_batch_id,
            total_items=len(items),
            reversible_items=sum(items_by_section.values()),
            items_by_section=items_by_section,
            missing_items=missing_items,
            failed_items=sum(1 for item in items if item.status == RESTORE_ITEM_STATUS_FAILED),
            warning_codes=warning_codes,
        )

    async def rollback(
        self,
        *,
        restore_batch_id: str,
        manager: MemoryManager,
        rolled_back_at: datetime,
    ) -> list[MemoryArchiveRestoreMutationRef]:
        items = await self.list_items(restore_batch_id)
        refs: list[MemoryArchiveRestoreMutationRef] = []
        refs.extend(await self._rollback_memory_items(manager=manager, items=items, rolled_back_at=rolled_back_at))
        refs.extend(await self._rollback_orm_items(items=items, rolled_back_at=rolled_back_at))
        return refs

    async def list_items(self, batch_id: str) -> list[MemoryArchiveRestoreItemModel]:
        result = await self._db.execute(
            select(MemoryArchiveRestoreItemModel)
            .where(MemoryArchiveRestoreItemModel.batch_id == batch_id)
            .order_by(MemoryArchiveRestoreItemModel.created_at, MemoryArchiveRestoreItemModel.id)
        )
        return list(result.scalars().all())

    async def _rollback_memory_items(
        self,
        *,
        manager: MemoryManager,
        items: list[MemoryArchiveRestoreItemModel],
        rolled_back_at: datetime,
    ) -> list[MemoryArchiveRestoreMutationRef]:
        refs: list[MemoryArchiveRestoreMutationRef] = []
        memory_items = [
            item
            for item in items
            if item.section == "memory" and item.status == RESTORE_ITEM_STATUS_RESTORED and not item.item_kind.endswith(".profile")
        ]
        ids_by_type = _memory_ids_by_type(memory_items)
        result = await manager.delete_memories_by_ids(ids_by_type)
        deleted = {(ref.memory_type, ref.memory_id) for ref in result.deleted_refs}
        missing = {(ref.memory_type, ref.memory_id) for ref in result.missing_refs}
        failed = {(ref.memory_type, ref.memory_id) for ref in result.failed_refs + result.forbidden_refs}
        for item in memory_items:
            refs.append(self._mark_memory_item(item, deleted=deleted, missing=missing, failed=failed, rolled_back_at=rolled_back_at))
        for item in _profile_items(items):
            refs.append(await self._rollback_profile_item(manager, item, rolled_back_at))
        return refs

    def _mark_memory_item(
        self,
        item: MemoryArchiveRestoreItemModel,
        *,
        deleted: set[tuple[str, str]],
        missing: set[tuple[str, str]],
        failed: set[tuple[str, str]],
        rolled_back_at: datetime,
    ) -> MemoryArchiveRestoreMutationRef:
        metadata = object_dict(item.metadata_json)
        memory_type = str(metadata.get("memory_type") or "")
        memory_ids = _string_list(metadata.get("memory_ids"))
        item_refs = {(memory_type, memory_id) for memory_id in memory_ids}
        if item_refs and item_refs.issubset(deleted):
            mark_restore_item(item, status=RESTORE_ITEM_STATUS_ROLLED_BACK, rolled_back_at=rolled_back_at)
            return item_to_ref(item, RESTORE_ITEM_STATUS_ROLLED_BACK)
        status = RESTORE_ITEM_STATUS_MISSING if item_refs & missing else RESTORE_ITEM_STATUS_FAILED if item_refs & failed else RESTORE_ITEM_STATUS_MISSING
        mark_restore_item(item, status=status, rolled_back_at=rolled_back_at, reason="memory_target_not_deleted")
        return item_to_ref(item, status, "memory_target_not_deleted")

    async def _rollback_profile_item(
        self,
        manager: MemoryManager,
        item: MemoryArchiveRestoreItemModel,
        rolled_back_at: datetime,
    ) -> MemoryArchiveRestoreMutationRef:
        metadata = object_dict(item.metadata_json)
        profile_key = str(metadata.get("profile_key") or "")
        if not profile_key:
            mark_restore_item(item, status=RESTORE_ITEM_STATUS_FAILED, rolled_back_at=rolled_back_at, reason="profile_key_missing")
            return item_to_ref(item, RESTORE_ITEM_STATUS_FAILED, "profile_key_missing")
        current = await manager.get_profile_attribute_snapshot(profile_key)
        imported_revision = str(metadata.get("profile_imported_revision") or "")
        imported_value = metadata.get("profile_imported_value")
        imported_present = bool(metadata.get("profile_imported_present"))
        if imported_revision and (not current.exists or current.revision != imported_revision):
            mark_restore_item(item, status=RESTORE_ITEM_STATUS_CONFLICT, rolled_back_at=rolled_back_at, reason="profile_changed_after_restore")
            return item_to_ref(item, RESTORE_ITEM_STATUS_CONFLICT, "profile_changed_after_restore")
        if not imported_revision and imported_present and current.value != imported_value:
            mark_restore_item(item, status=RESTORE_ITEM_STATUS_CONFLICT, rolled_back_at=rolled_back_at, reason="profile_changed_after_restore")
            return item_to_ref(item, RESTORE_ITEM_STATUS_CONFLICT, "profile_changed_after_restore")
        restore_value = str(metadata.get("profile_previous_value")) if metadata.get("profile_previous_present") else None
        restored_count = await manager.restore_profile_attributes({profile_key: restore_value})
        status = RESTORE_ITEM_STATUS_ROLLED_BACK if restored_count else RESTORE_ITEM_STATUS_FAILED
        mark_restore_item(item, status=status, rolled_back_at=rolled_back_at, reason="" if restored_count else "profile_restore_failed")
        return item_to_ref(item, status, "" if restored_count else "profile_restore_failed")

    async def _rollback_orm_items(
        self,
        *,
        items: list[MemoryArchiveRestoreItemModel],
        rolled_back_at: datetime,
    ) -> list[MemoryArchiveRestoreMutationRef]:
        refs: list[MemoryArchiveRestoreMutationRef] = []
        for item_kind, model in _rollback_models():
            for item in [entry for entry in items if entry.item_kind == item_kind and entry.status == RESTORE_ITEM_STATUS_RESTORED]:
                target_id = item.target_id or ""
                row = await self._db.get(model, target_id)
                if row is None:
                    mark_restore_item(item, status=RESTORE_ITEM_STATUS_MISSING, rolled_back_at=rolled_back_at, reason="target_missing")
                    refs.append(item_to_ref(item, RESTORE_ITEM_STATUS_MISSING, "target_missing"))
                    continue
                await self._db.delete(row)
                mark_restore_item(item, status=RESTORE_ITEM_STATUS_ROLLED_BACK, rolled_back_at=rolled_back_at)
                refs.append(item_to_ref(item, RESTORE_ITEM_STATUS_ROLLED_BACK))
        await self._db.flush()
        return refs

    async def _target_exists(self, item: MemoryArchiveRestoreItemModel) -> bool:
        if item.section == "memory":
            return item.status == RESTORE_ITEM_STATUS_RESTORED
        model = dict(_rollback_models()).get(item.item_kind)
        if model is None or not item.target_id:
            return False
        row = await self._db.get(model, item.target_id)
        return row is not None


def _memory_ids_by_type(items: list[MemoryArchiveRestoreItemModel]) -> dict[str, list[str]]:
    ids_by_type: dict[str, list[str]] = {}
    for item in items:
        metadata = object_dict(item.metadata_json)
        memory_type = str(metadata.get("memory_type") or "")
        ids_by_type.setdefault(memory_type, []).extend(_string_list(metadata.get("memory_ids")))
    return ids_by_type


def _profile_items(items: list[MemoryArchiveRestoreItemModel]) -> list[MemoryArchiveRestoreItemModel]:
    return [
        item
        for item in items
        if item.section == "memory" and item.item_kind.endswith(".profile") and item.status == RESTORE_ITEM_STATUS_RESTORED
    ]


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _rollback_models() -> tuple[tuple[str, type[object]], ...]:
    return (
        ("audit.event", MemoryOperationEventModel),
        ("replay.turn", AgentTurn),
        ("conversation.chat", Chat),
        ("shared_context.proposal", SharedContextWriteProposalModel),
        ("shared_context.binding", SharedContextBindingModel),
        ("shared_context.context", SharedContextModel),
    )
