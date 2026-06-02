"""Memory import session data helpers.

[INPUT]
app.services.memory.import_session_models::NormalizedMemoryData (POS: 记忆导入会话 DTO 层),
myrm_agent_harness.toolkits.memory::MemoryManager (POS: Unified memory manager and core facade of the Memory Toolkit)

[OUTPUT]
canonical_hash, normalized_to_json, normalized_from_json, attach_import_metadata,
build_transaction_items, summary_unmapped_count, capture_profile_previous_values,
capture_profile_imported_values: import session data transformation helpers.

[POS]
记忆导入会话数据转换层。负责 payload 指纹、normalized data JSON 转换、导入 metadata 注入和 profile 导入前后值采集。
"""

from __future__ import annotations

import hashlib
import json

from myrm_agent_harness.toolkits.memory import (
    MemoryImportPlan,
    MemoryImportPlanItem,
    MemoryManager,
    MemoryType,
    ProfileAttributeSnapshot,
)

from app.services.memory.import_session_models import NormalizedMemoryData


def canonical_hash(value: dict[str, object]) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def normalized_to_json(data: NormalizedMemoryData) -> dict[str, object]:
    return {bucket: entries for bucket, entries in data.items()}


def normalized_from_json(value: dict[str, object]) -> NormalizedMemoryData:
    normalized: NormalizedMemoryData = {}
    for bucket, raw_entries in value.items():
        if not isinstance(raw_entries, list):
            continue
        entries: list[dict[str, object]] = []
        for raw_entry in raw_entries:
            if isinstance(raw_entry, dict):
                entries.append({str(key): item for key, item in raw_entry.items()})
        normalized[str(bucket)] = entries
    return normalized


def attach_import_metadata(
    data: NormalizedMemoryData,
    *,
    import_batch_id: str,
    source: str,
    dry_run_id: str,
    payload_hash: str,
) -> NormalizedMemoryData:
    enriched: NormalizedMemoryData = {}
    metadata = {
        "import_batch_id": import_batch_id,
        "import_source": source,
        "import_dry_run_id": dry_run_id,
        "import_payload_hash": payload_hash,
    }
    for bucket, entries in data.items():
        enriched[bucket] = []
        for index, entry in enumerate(entries):
            raw_metadata = entry.get("metadata")
            entry_metadata = raw_metadata if isinstance(raw_metadata, dict) else {}
            enriched_entry = dict(entry)
            import_item_id = f"{import_batch_id}:{bucket}:{index}"
            enriched_entry["metadata"] = {**entry_metadata, **metadata, "import_item_id": import_item_id}
            enriched[bucket].append(enriched_entry)
    return enriched


def build_import_plan(
    data: NormalizedMemoryData,
    *,
    dry_run_id: str,
    skip_duplicates: bool,
) -> MemoryImportPlan:
    items: list[MemoryImportPlanItem] = []
    for bucket, entries in data.items():
        for index, _entry in enumerate(entries):
            items.append(
                MemoryImportPlanItem(
                    item_id=f"{dry_run_id}:{bucket}:{index}",
                    memory_type=bucket,
                    status="planned",
                )
            )
    plan_hash = canonical_hash(
        {
            "version": 1,
            "dry_run_id": dry_run_id,
            "skip_duplicates": skip_duplicates,
            "normalized_data": data,
        }
    )
    return MemoryImportPlan(
        plan_hash=plan_hash,
        skip_duplicates=skip_duplicates,
        planned_items=len(items),
        items=items,
    )


def build_transaction_items(
    data: NormalizedMemoryData,
    *,
    stored_refs: dict[str, list[dict[str, str]]],
    profile_previous_values: dict[str, ProfileAttributeSnapshot],
    profile_imported_values: dict[str, ProfileAttributeSnapshot],
) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    refs_by_item = _stored_refs_by_import_item(stored_refs)
    for bucket, entries in data.items():
        for entry in entries:
            metadata = entry.get("metadata")
            if not isinstance(metadata, dict):
                continue
            item_id = metadata.get("import_item_id")
            if not isinstance(item_id, str):
                continue
            profile_key = profile_entry_key(entry) if bucket == MemoryType.PROFILE.value else None
            memory_ids = [] if profile_key else refs_by_item.get(item_id, [])
            previous_snapshot = profile_previous_values.get(profile_key) if profile_key else None
            imported_snapshot = profile_imported_values.get(profile_key) if profile_key else None
            profile_previous_present = bool(previous_snapshot and previous_snapshot.exists)
            profile_imported_present = bool(imported_snapshot and imported_snapshot.exists)
            status = "imported" if memory_ids or (profile_key and profile_imported_present) else "skipped"
            items.append(
                {
                    "item_id": item_id,
                    "memory_type": bucket,
                    "status": status,
                    "memory_ids": memory_ids,
                    "profile_key": profile_key,
                    "profile_previous_value": previous_snapshot.value if previous_snapshot else None,
                    "profile_imported_value": imported_snapshot.value if imported_snapshot else None,
                    "profile_previous_value_present": profile_previous_present,
                    "profile_imported_value_present": profile_imported_present,
                    "profile_previous_revision": previous_snapshot.revision if previous_snapshot else "",
                    "profile_imported_revision": imported_snapshot.revision if imported_snapshot else "",
                }
            )
    return items


def summary_unmapped_count(value: dict[str, object]) -> int:
    raw = value.get("unmapped_items")
    return raw if isinstance(raw, int) else 0


async def capture_profile_previous_values(
    manager: MemoryManager, data: NormalizedMemoryData
) -> dict[str, ProfileAttributeSnapshot]:
    previous: dict[str, ProfileAttributeSnapshot] = {}
    for entry in data.get(MemoryType.PROFILE.value, []):
        key = profile_entry_key(entry)
        if key and key not in previous:
            previous[key] = await manager.get_profile_attribute_snapshot(key)
    return previous


async def capture_profile_imported_values(
    manager: MemoryManager, data: NormalizedMemoryData
) -> dict[str, ProfileAttributeSnapshot]:
    imported: dict[str, ProfileAttributeSnapshot] = {}
    for entry in data.get(MemoryType.PROFILE.value, []):
        key = profile_entry_key(entry)
        if key and key not in imported:
            imported[key] = await manager.get_profile_attribute_snapshot(key)
    return imported


def profile_entry_key(entry: dict[str, object]) -> str | None:
    raw_key = entry.get("key")
    if isinstance(raw_key, str) and raw_key:
        return raw_key
    metadata = entry.get("metadata")
    if not isinstance(metadata, dict):
        return None
    metadata_key = metadata.get("key")
    return metadata_key if isinstance(metadata_key, str) and metadata_key else None


def _stored_refs_by_import_item(stored_refs: dict[str, list[dict[str, str]]]) -> dict[str, list[str]]:
    refs_by_item: dict[str, list[str]] = {}
    for refs in stored_refs.values():
        for ref in refs:
            import_item_id = ref.get("import_item_id")
            memory_id = ref.get("id")
            if import_item_id and memory_id:
                refs_by_item.setdefault(import_item_id, []).append(memory_id)
    return refs_by_item
