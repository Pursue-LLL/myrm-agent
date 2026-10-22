"""Model-assisted lane of the pasted memory import.

[INPUT]
app.services.memory.imports.import_pasted::refusal_result (POS: 粘贴通道显式拒绝结果)
app.services.memory.imports.import_adapter_utils::build_metadata (POS: 适配器共享工具)

[OUTPUT]
MODEL_BUCKETS, dry_run_pasted_model_items: model-extracted entries mapped into
native buckets with the same review pipeline as the deterministic lane.

[POS]
Optional lane of the paste import: entries the configured model distilled from
free text are shaped into profile / procedural / semantic / episodic buckets.
The lane never persists anything and never bypasses review; callers fall back to
the deterministic parser when no model is configured or extraction fails.
"""

from __future__ import annotations

from myrm_agent_harness.toolkits.memory import (
    MemoryImportDryRunResult,
    MemoryImportMappingItem,
)

from app.services.memory.imports.import_adapter_utils import (
    build_metadata,
    build_result,
    iso_or_now,
)
from app.services.memory.imports.import_pasted import (
    BUCKET_PROCEDURAL,
    BUCKET_PROFILE,
    BUCKET_SEMANTIC,
    WARNING_PASTED_EMPTY,
    WARNING_PASTED_MODEL_FALLBACK,
    refusal_result,
)

# Buckets the model-assisted lane can fill, mirroring the deterministic lane.
MODEL_BUCKETS = (
    BUCKET_PROFILE,
    BUCKET_PROCEDURAL,
    BUCKET_SEMANTIC,
    "episodic",
)


def dry_run_pasted_model_items(
    items: list[object],
    *,
    extraction_failed: bool = False,
) -> MemoryImportDryRunResult:
    """Build a paste-lane result from model-extracted items."""

    normalized: dict[str, list[dict[str, object]]] = {}
    for raw in items:
        if not isinstance(raw, dict):
            continue
        content = str(raw.get("content", "")).strip()
        if not content:
            continue
        bucket = str(raw.get("bucket", BUCKET_SEMANTIC)).strip()
        if bucket not in MODEL_BUCKETS:
            bucket = BUCKET_SEMANTIC
        normalized.setdefault(bucket, []).append(_model_item(raw, content=content, bucket=bucket))

    if not normalized:
        return refusal_result(
            WARNING_PASTED_EMPTY,
            "The model could not find any memories in the pasted text.",
        )

    mappings: list[MemoryImportMappingItem] = []
    mapped_items = 0
    for bucket in MODEL_BUCKETS:
        bucket_items = normalized.get(bucket, [])
        if not bucket_items:
            continue
        mapped_items += len(bucket_items)
        mappings.append(
            MemoryImportMappingItem(
                source_bucket="model_extracted_entries",
                target_bucket=bucket,
                status="mapped",
                item_count=len(bucket_items),
                imported_count=len(bucket_items),
            ),
        )

    return build_result(
        source="pasted_memory",
        version="1",
        normalized=normalized,
        mappings=mappings,
        mapped_items=mapped_items,
        unmapped_items=0,
        warnings=[WARNING_PASTED_MODEL_FALLBACK] if extraction_failed else [],
    )


def _model_item(raw: dict[str, object], *, content: str, bucket: str) -> dict[str, object]:
    """Shape one extracted memory into the native bucket item."""

    metadata = build_metadata(
        "pasted_memory",
        {"extraction": "model"},
        ("extraction",),
    )
    item: dict[str, object] = {
        "content": content,
        "created_at": iso_or_now(None),
        "metadata": metadata,
    }
    if bucket == BUCKET_PROFILE:
        profile_key = str(raw.get("profile_key", "")).strip()
        if profile_key:
            item["key"] = profile_key
        item["value"] = str(raw.get("profile_value", "")).strip() or content
        item["importance"] = 0.75
        item["confidence"] = 0.8
        item["tags"] = ["pasted_memory", "profile"]
        return item
    if bucket == BUCKET_PROCEDURAL:
        trigger = str(raw.get("trigger", "")).strip()
        item["priority"] = 5
        item["trigger_keywords"] = [trigger] if trigger else ["pasted_memory"]
        item["tags"] = ["pasted_memory", "rule"]
        return item
    item["importance"] = _bounded_float(raw.get("importance"), default=0.7)
    item["confidence"] = _bounded_float(raw.get("confidence"), default=0.75)
    item["tags"] = ["pasted_memory"]
    return item


def _bounded_float(value: object, *, default: float) -> float:
    try:
        number = float(str(value))
    except (TypeError, ValueError):
        return default
    return min(1.0, max(0.0, number))
