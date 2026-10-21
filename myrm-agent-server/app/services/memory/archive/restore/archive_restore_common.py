"""Shared primitives for Memory Archive restore services.

[INPUT]
myrm_agent_harness.toolkits.memory::MemoryArchiveRestoreMutationRef (POS: framework archive restore DTOs)

[OUTPUT]
Constants, validation helpers, mutation-ref builders, and JSON coercion helpers.

[POS]
单用户 Memory Archive 恢复内部工具层。只提供无业务副作用的纯辅助能力。
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import cast
from uuid import uuid4

from myrm_agent_harness.toolkits.memory import (
    MemoryArchiveRestoreItemStatus,
    MemoryArchiveRestoreMutationRef,
    MemoryArchiveSectionName,
    MemoryOperationStatus,
)

from app.database.models.memory import MemoryArchiveRestoreItemModel

RESTORE_BATCH_STATUS_IN_PROGRESS: str = "in_progress"
RESTORE_BATCH_STATUS_CONFIRMED: str = "confirmed"
RESTORE_BATCH_STATUS_FAILED: str = "failed"
RESTORE_BATCH_STATUS_ROLLBACK_IN_PROGRESS: str = "rollback_in_progress"
RESTORE_BATCH_STATUS_ROLLED_BACK: str = "rolled_back"
RESTORE_BATCH_STATUS_PARTIAL: str = "partial"
RESTORE_BATCH_STATUS_ROLLBACK_FAILED: str = "rollback_failed"

RESTORE_ITEM_STATUS_RESTORED: MemoryArchiveRestoreItemStatus = "restored"
RESTORE_ITEM_STATUS_SKIPPED: MemoryArchiveRestoreItemStatus = "skipped"
RESTORE_ITEM_STATUS_CONFLICT: MemoryArchiveRestoreItemStatus = "conflict"
RESTORE_ITEM_STATUS_MISSING: MemoryArchiveRestoreItemStatus = "missing"
RESTORE_ITEM_STATUS_FAILED: MemoryArchiveRestoreItemStatus = "failed"
RESTORE_ITEM_STATUS_ROLLED_BACK: MemoryArchiveRestoreItemStatus = "rolled_back"

DEFAULT_ARCHIVE_RESTORE_SECTIONS: tuple[MemoryArchiveSectionName, ...] = (
    "memory",
    "shared_context",
    "conversation",
    "replay",
    "audit",
)


class MemoryArchiveRestoreError(Exception):
    """Raised when an archive restore request cannot be completed."""

    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


def selected_sections(sections: Sequence[MemoryArchiveSectionName] | None) -> tuple[MemoryArchiveSectionName, ...]:
    if sections is None:
        return DEFAULT_ARCHIVE_RESTORE_SECTIONS
    return tuple(section for section in DEFAULT_ARCHIVE_RESTORE_SECTIONS if section in sections)


def operation_status(*, conflict_items: int, failed_items: int) -> MemoryOperationStatus:
    if failed_items > 0:
        return MemoryOperationStatus.ERROR
    if conflict_items > 0:
        return MemoryOperationStatus.WARNING
    return MemoryOperationStatus.SUCCESS


def count_items(value: object) -> int:
    if isinstance(value, list):
        return len(value)
    if isinstance(value, dict):
        return sum(count_items(item) for item in value.values())
    return 0


def object_dict(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        return {}
    return {str(key): item for key, item in value.items()}


def object_rows(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [object_dict(item) for item in value if isinstance(item, dict)]


def optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None


def int_value(value: object, default: int = 0) -> int:
    return value if isinstance(value, int) else default


def optional_int(value: object) -> int | None:
    return value if isinstance(value, int) else None


def parse_datetime(value: object) -> datetime:
    return parse_datetime_or_none(value) or datetime.now(UTC)


def parse_datetime_or_none(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def refs_by_import_item(stored_refs: dict[str, list[dict[str, str]]]) -> dict[str, list[str]]:
    refs: dict[str, list[str]] = {}
    for bucket_refs in stored_refs.values():
        for ref in bucket_refs:
            import_item_id = ref.get("import_item_id")
            memory_id = ref.get("id")
            if import_item_id and memory_id:
                refs.setdefault(import_item_id, []).append(memory_id)
    return refs


def make_ref(
    *,
    section: MemoryArchiveSectionName,
    item_kind: str,
    source_id: str = "",
    target_id: str = "",
    status: MemoryArchiveRestoreItemStatus,
    reason: str = "",
) -> MemoryArchiveRestoreMutationRef:
    return MemoryArchiveRestoreMutationRef(
        section=section,
        item_kind=item_kind,
        source_id=source_id,
        target_id=target_id,
        status=status,
        reason=reason,
    )


def item_to_ref(
    item: MemoryArchiveRestoreItemModel,
    status: MemoryArchiveRestoreItemStatus,
    reason: str = "",
) -> MemoryArchiveRestoreMutationRef:
    return make_ref(
        section=cast(MemoryArchiveSectionName, item.section),
        item_kind=item.item_kind,
        source_id=item.source_id or "",
        target_id=item.target_id or "",
        status=status,
        reason=reason,
    )


def add_restore_item(
    *,
    batch_id: str,
    ref: MemoryArchiveRestoreMutationRef,
    metadata: dict[str, object] | None = None,
) -> MemoryArchiveRestoreItemModel:
    return MemoryArchiveRestoreItemModel(
        id=f"{batch_id}:{ref.item_kind}:{ref.source_id or ref.target_id or uuid4().hex}",
        batch_id=batch_id,
        section=ref.section,
        item_kind=ref.item_kind,
        source_id=ref.source_id or None,
        target_id=ref.target_id or None,
        status=ref.status,
        created_at=datetime.now(UTC),
        metadata_json=dict(metadata or {}),
    )


def mark_restore_item(
    item: MemoryArchiveRestoreItemModel,
    *,
    status: MemoryArchiveRestoreItemStatus,
    rolled_back_at: datetime,
    reason: str = "",
) -> None:
    item.status = status
    item.rollback_status = status
    item.rollback_error = reason or None
    item.rolled_back_at = rolled_back_at
