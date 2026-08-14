"""Mem0 memory import adapter.

[INPUT]
Mem0 data payload with exported memories in their native format.

Expected payload keys:
  - ``memories``: list[dict] — Mem0 memory items (with fields: id, memory, metadata, created_at, updated_at)
  - ``_source``: "mem0" — source identifier

[OUTPUT]
MemoryImportDryRunResult mapping Mem0 data to native semantic memory bucket.

[POS]
Mem0 competitor import adapter. Maps Mem0's flat memory list into the native
semantic bucket for the dry-run → confirm → rollback pipeline.
Mem0 stores memories as flat text strings; we map all to semantic type.
"""

from __future__ import annotations

from myrm_agent_harness.toolkits.memory import (
    MemoryImportDryRunResult,
    MemoryImportMappingItem,
)

from app.services.memory.import_adapter_utils import (
    build_metadata,
    build_result,
    float_between,
    iso_or_now,
    text,
)


def dry_run_mem0(payload: dict[str, object]) -> MemoryImportDryRunResult:
    """Map a Mem0 data payload into native memory buckets without persisting."""

    normalized: dict[str, list[dict[str, object]]] = {}
    mappings: list[MemoryImportMappingItem] = []
    warnings: list[str] = []
    mapped_items = 0
    unmapped_items = 0

    memories = payload.get("memories")
    if not isinstance(memories, list):
        memories_alt = payload.get("results")
        if isinstance(memories_alt, list):
            memories = memories_alt
        else:
            warnings.append("mem0_no_memories_found")
            mappings.append(
                MemoryImportMappingItem(
                    source_bucket="memories",
                    target_bucket="semantic",
                    status="unsupported",
                    item_count=0,
                    reason="No memories array found in payload",
                )
            )
            return build_result(
                source="mem0",
                version="1",
                normalized=normalized,
                mappings=mappings,
                mapped_items=0,
                unmapped_items=0,
                warnings=warnings,
            )

    semantic_items: list[dict[str, object]] = []

    for raw_item in memories:
        if not isinstance(raw_item, dict):
            unmapped_items += 1
            continue

        content = text(raw_item.get("memory") or raw_item.get("text", ""))
        if not content:
            unmapped_items += 1
            continue

        item_metadata = raw_item.get("metadata")
        meta_dict = item_metadata if isinstance(item_metadata, dict) else {}

        semantic_item: dict[str, object] = {
            "content": content,
            "importance": float_between(meta_dict.get("importance"), 0.5),
            "created_at": iso_or_now(raw_item.get("created_at")),
            "updated_at": iso_or_now(raw_item.get("updated_at")),
            "metadata": build_metadata("mem0", raw_item, ("id", "hash", "user_id", "agent_id")),
        }

        tags = meta_dict.get("tags")
        if isinstance(tags, list):
            semantic_item["tags"] = [str(t) for t in tags if isinstance(t, str)]

        semantic_items.append(semantic_item)
        mapped_items += 1

    if semantic_items:
        normalized["semantic"] = semantic_items

    mappings.append(
        MemoryImportMappingItem(
            source_bucket="memories",
            target_bucket="semantic",
            status="mapped" if semantic_items else "dropped",
            item_count=len(semantic_items),
        )
    )

    return build_result(
        source="mem0",
        version="1",
        normalized=normalized,
        mappings=mappings,
        mapped_items=mapped_items,
        unmapped_items=unmapped_items,
        warnings=warnings,
    )


def is_mem0_payload(payload: dict[str, object]) -> bool:
    """Detect Mem0 data payload by source tag or structure."""

    if payload.get("_source") == "mem0":
        return True
    memories = payload.get("memories")
    if isinstance(memories, list) and memories:
        first = memories[0]
        if isinstance(first, dict) and "memory" in first:
            return True
    return False
