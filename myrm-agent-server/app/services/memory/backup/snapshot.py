"""Portable memory snapshot: the single data contract of memory backup.

[INPUT]
myrm_agent_harness.toolkits.memory::MemoryManager/MemoryType (POS: 记忆框架门面；export_all/import_memories 是其与 embedding 无关的可移植导出/导入契约)

[OUTPUT]
SNAPSHOT_MEMORY_TYPES / MemorySnapshot / SnapshotError / capture_snapshot / apply_snapshot / encode_snapshot / decode_snapshot

[POS]
本地卷备份与远程（WebDAV/S3）备份共用的快照格式及其捕获/回放逻辑。快照只含记忆内容，不含向量，
恢复时由 MemoryManager 重新计算 embedding；捕获与回放都会校验完整性，宁可失败也不静默丢记忆。
"""

from __future__ import annotations

import gzip
import json
import logging
import zlib
from datetime import UTC, datetime
from typing import Final

from myrm_agent_harness.toolkits.memory import MemoryManager, MemoryType
from pydantic import BaseModel, ValidationError, field_validator

logger = logging.getLogger(__name__)

SNAPSHOT_VERSION: Final = 3

# The user-memory types MemoryManager.get_enabled_types() designates: the ones export_all()
# lists, import_memories() writes back and delete_by_type() can clear. Task digests already
# live in the episodic collection, CLAIM/INTEGRATION are derived and not listable, and the
# verbatim CONVERSATION channel can neither be cleared nor deduplicated on restore.
SNAPSHOT_MEMORY_TYPES: Final[tuple[MemoryType, ...]] = (
    MemoryType.PROFILE,
    MemoryType.PROCEDURAL,
    MemoryType.SEMANTIC,
    MemoryType.EPISODIC,
)
_SNAPSHOT_TYPE_NAMES: Final = frozenset(memory_type.value for memory_type in SNAPSHOT_MEMORY_TYPES)

# Merging relies on the framework's deduplicator for semantic memories and on upserts for profile keys. Rules (no
# natural key) and episodic events (never merged) have no such guard, so merge skips entries whose identifying
# fields match a stored one; these fields survive an export/import round trip, unlike ids and timestamps.
_MERGE_IDENTITY_FIELDS: Final[dict[MemoryType, tuple[str, ...]]] = {
    MemoryType.PROCEDURAL: ("trigger", "action", "content"),
    MemoryType.EPISODIC: ("event_type", "content"),
}
_STORED_LOOKUP_LIMIT: Final = 10_000


class SnapshotError(Exception):
    """A snapshot could not be captured, decoded or applied; the message is safe to show to the user."""


class MemorySnapshot(BaseModel):
    """Serialized memories keyed by memory type, exactly as ``MemoryManager.export_all()`` yields them."""

    version: int = SNAPSHOT_VERSION
    created_at: datetime
    memories: dict[str, list[dict[str, object]]]

    @field_validator("memories")
    @classmethod
    def _only_snapshot_types(cls, memories: dict[str, list[dict[str, object]]]) -> dict[str, list[dict[str, object]]]:
        unsupported = sorted(set(memories) - _SNAPSHOT_TYPE_NAMES)
        if unsupported:
            raise ValueError(f"unsupported memory types: {', '.join(unsupported)}")
        return memories

    @property
    def memory_count(self) -> int:
        return sum(len(entries) for entries in self.memories.values())


async def capture_snapshot(manager: MemoryManager) -> MemorySnapshot:
    """Export every snapshot type, failing when any type came back incomplete.

    ``export_all`` caps each type and swallows per-type errors, so a short result would
    otherwise look like a successful backup. Counts are read first: memories written while
    exporting only add rows, hence fewer exported than counted means truncation or a failure.
    """
    expected = {memory_type: await manager.count_memories(memory_type) for memory_type in SNAPSHOT_MEMORY_TYPES}
    exported = await manager.export_all()

    memories: dict[str, list[dict[str, object]]] = {}
    incomplete: list[str] = []
    for memory_type in SNAPSHOT_MEMORY_TYPES:
        entries = exported.get(memory_type.value, [])
        if entries:
            memories[memory_type.value] = entries
        if len(entries) < expected[memory_type]:
            incomplete.append(f"{memory_type.value} ({len(entries)} of {expected[memory_type]})")
    if incomplete:
        raise SnapshotError(f"Backup would be incomplete, nothing was saved: {', '.join(incomplete)}")
    return MemorySnapshot(created_at=datetime.now(UTC), memories=memories)


async def apply_snapshot(manager: MemoryManager, snapshot: MemorySnapshot, *, replace: bool) -> dict[str, int]:
    """Write a snapshot into the manager and return how many entries each type stored.

    ``replace`` makes the store equal to the snapshot: every snapshot type is cleared first,
    entries are imported without deduplication and each one must land. Otherwise the
    snapshot is merged: entries the store already holds are skipped.
    """
    if manager.approval_required:
        raise SnapshotError("Restore needs a memory manager that stores directly, not through the approval queue")

    if replace:
        await _clear_snapshot_types(manager)
    entries = snapshot.memories if replace else await _without_stored_duplicates(manager, snapshot.memories)
    counts = await manager.import_memories(entries, skip_duplicates=not replace)

    if replace:
        short = [
            f"{name} ({counts.get(name, 0)} of {len(items)})"
            for name, items in entries.items()
            if counts.get(name, 0) < len(items)
        ]
        if short:
            raise SnapshotError(f"Restore incomplete: {', '.join(short)}")
    return counts


async def _clear_snapshot_types(manager: MemoryManager) -> None:
    for memory_type in SNAPSHOT_MEMORY_TYPES:
        await manager.delete_by_type(memory_type)
    remaining = [memory_type.value for memory_type in SNAPSHOT_MEMORY_TYPES if await manager.count_memories(memory_type) > 0]
    if remaining:
        raise SnapshotError(f"Could not clear existing memories ({', '.join(remaining)}), nothing was restored")


async def _without_stored_duplicates(
    manager: MemoryManager, memories: dict[str, list[dict[str, object]]]
) -> dict[str, list[dict[str, object]]]:
    """Drop entries the store already holds for the types whose import path never deduplicates."""
    filtered = dict(memories)
    for memory_type, fields in _MERGE_IDENTITY_FIELDS.items():
        entries = memories.get(memory_type.value)
        if not entries:
            continue
        stored = await manager.list_memories(memory_type, limit=_STORED_LOOKUP_LIMIT)
        known = {_identity(item.model_dump(mode="json"), fields) for item in stored}
        filtered[memory_type.value] = [entry for entry in entries if _identity(entry, fields) not in known]
    return filtered


def _identity(entry: dict[str, object], fields: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(str(entry.get(field) or "") for field in fields)


def encode_snapshot(snapshot: MemorySnapshot) -> bytes:
    return gzip.compress(snapshot.model_dump_json().encode("utf-8"), compresslevel=6)


def decode_snapshot(data: bytes) -> MemorySnapshot:
    try:
        raw = json.loads(gzip.decompress(data))
    except (OSError, EOFError, zlib.error, ValueError) as exc:
        raise SnapshotError("Backup file is corrupt or is not a Myrm memory backup") from exc
    version = raw.get("version") if isinstance(raw, dict) else None
    if version != SNAPSHOT_VERSION:
        raise SnapshotError(f"Unsupported backup format version: {version!r}")
    try:
        return MemorySnapshot.model_validate(raw)
    except ValidationError as exc:
        raise SnapshotError("Backup file has an invalid structure") from exc
