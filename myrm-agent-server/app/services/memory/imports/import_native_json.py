"""Native JSON memory import adapter.

[INPUT]
Raw dict payload with optional ``data`` wrapper containing profile/semantic/episodic/procedural buckets.

[OUTPUT]
MemoryImportDryRunResult with mapped native memory items.

[POS]
Pure native-JSON dry-run adapter extracted from import_adapters.py for single-responsibility.
"""

from __future__ import annotations

from myrm_agent_harness.toolkits.memory import (
    MemoryImportDryRunResult,
    MemoryImportMappingItem,
)

from app.services.memory.import_adapter_utils import (
    SUPPORTED_NATIVE_BUCKETS,
    WARNING_NO_NATIVE_BUCKETS,
    build_result,
    object_dict,
)


def dry_run_native_json(payload: dict[str, object]) -> MemoryImportDryRunResult:
    """Map a native JSON payload into memory buckets without persisting."""

    version = str(payload.get("version") or "1")
    raw_data = payload.get("data")
    source_data = object_dict(raw_data) if isinstance(raw_data, dict) else payload

    normalized: dict[str, list[dict[str, object]]] = {}
    mappings: list[MemoryImportMappingItem] = []
    warnings: list[str] = []
    mapped_items = 0
    unmapped_items = 0

    for bucket, raw_entries in source_data.items():
        if not isinstance(raw_entries, list):
            continue
        item_count = len(raw_entries)
        if bucket not in SUPPORTED_NATIVE_BUCKETS:
            unmapped_items += item_count
            mappings.append(
                MemoryImportMappingItem(
                    source_bucket=bucket,
                    status="unsupported",
                    item_count=item_count,
                    unmapped_count=item_count,
                    reason="Native import accepts profile, semantic, episodic, and procedural buckets.",
                )
            )
            continue
        entries = [object_dict(entry) for entry in raw_entries if isinstance(entry, dict)]
        dropped = item_count - len(entries)
        normalized[bucket] = entries
        mapped_items += len(entries)
        unmapped_items += dropped
        mappings.append(
            MemoryImportMappingItem(
                source_bucket=bucket,
                target_bucket=bucket,
                status="mapped" if dropped == 0 else "partially_mapped",
                item_count=item_count,
                imported_count=len(entries),
                unmapped_count=dropped,
                reason="" if dropped == 0 else "Non-object rows are ignored.",
            )
        )

    if not normalized:
        warnings.append(WARNING_NO_NATIVE_BUCKETS)

    return build_result(
        source="native_json",
        version=version,
        normalized=normalized,
        mappings=mappings,
        mapped_items=mapped_items,
        unmapped_items=unmapped_items,
        warnings=warnings,
    )
