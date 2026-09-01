"""Windsurf memory import adapter.

[INPUT]
Windsurf data payload with memories and settings.

Expected payload keys (populated by frontend upload from Windsurf exports):
  - ``windsurf_memories``: list[dict] — memory entries (cascade memories)
  - ``windsurf_settings``: dict — Windsurf configuration
  - ``_source``: "windsurf" — source identifier

[OUTPUT]
MemoryImportDryRunResult mapping Windsurf data to native semantic/profile buckets.

[POS]
Windsurf competitor import adapter. Converts Windsurf cascade memories into
semantic memories and settings into profile memories. Memory Center
manual-import lane only; Wizard filesystem discovery stays a closed 5-source
set (see services/migration/_ARCH.md).
"""

from __future__ import annotations

from myrm_agent_harness.toolkits.memory import (
    MemoryImportDryRunResult,
    MemoryImportMappingItem,
)

from app.services.memory.imports.import_adapter_utils import (
    build_metadata,
    build_result,
    float_between,
    iso_or_now,
    object_dict,
    text,
)


def dry_run_windsurf(payload: dict[str, object]) -> MemoryImportDryRunResult:
    """Map a Windsurf data payload into native memory buckets without persisting."""

    normalized: dict[str, list[dict[str, object]]] = {}
    mappings: list[MemoryImportMappingItem] = []
    warnings: list[str] = []
    mapped_items = 0
    unmapped_items = 0

    memories = payload.get("windsurf_memories")
    if isinstance(memories, list) and memories:
        semantic_items = _parse_memories(memories)
        if semantic_items:
            normalized["semantic"] = semantic_items
            mapped_items += len(semantic_items)
        mappings.append(
            MemoryImportMappingItem(
                source_bucket="windsurf_memories",
                target_bucket="semantic",
                status="mapped" if semantic_items else "unsupported",
                item_count=len(memories),
                imported_count=len(semantic_items),
                reason="" if semantic_items else "No valid memory entries found.",
            )
        )

    profile_items: list[dict[str, object]] = []
    settings = payload.get("windsurf_settings")
    if isinstance(settings, dict) and settings:
        profile_items = _parse_settings(settings)
        if profile_items:
            normalized.setdefault("profile", []).extend(profile_items)
            mapped_items += len(profile_items)
        mappings.append(
            MemoryImportMappingItem(
                source_bucket="windsurf_settings",
                target_bucket="profile",
                status="mapped" if profile_items else "unsupported",
                item_count=1,
                imported_count=len(profile_items),
                reason="" if profile_items else "No importable settings found.",
            )
        )

    if not normalized:
        unmapped_items += 1
        warnings.append("windsurf_empty_payload")

    return build_result(
        source="windsurf",
        version="1",
        normalized=normalized,
        mappings=mappings,
        mapped_items=mapped_items,
        unmapped_items=unmapped_items,
        warnings=warnings,
    )


def _parse_memories(entries: list[object]) -> list[dict[str, object]]:
    """Convert Windsurf memory entries into semantic memory items."""

    items: list[dict[str, object]] = []
    for raw_entry in entries:
        if not isinstance(raw_entry, dict):
            continue
        entry = object_dict(raw_entry)
        content = (
            text(entry.get("content"))
            or text(entry.get("text"))
            or text(entry.get("memory"))
        )
        if not content:
            continue
        items.append(
            {
                "content": content,
                "importance": float_between(entry.get("importance"), 0.7),
                "confidence": float_between(entry.get("confidence"), 0.75),
                "tags": ["windsurf_memory"],
                "created_at": iso_or_now(
                    entry.get("created_at") or entry.get("timestamp")
                ),
                "metadata": build_metadata("windsurf", entry, ("id", "type")),
            }
        )
    return items


def _parse_settings(settings: object) -> list[dict[str, object]]:
    """Extract meaningful preferences from Windsurf settings as profile memories."""

    if not isinstance(settings, dict):
        return []
    typed = object_dict(settings)
    items: list[dict[str, object]] = []

    preferred_language = text(typed.get("preferredLanguage"))
    if preferred_language:
        items.append(
            {
                "content": f"Preferred programming language: {preferred_language}",
                "memory_type": "profile",
                "importance": 0.7,
                "confidence": 0.9,
                "tags": ["windsurf_preference", "language"],
                "created_at": iso_or_now(None),
                "metadata": build_metadata("windsurf", typed, ("preferredLanguage",)),
            }
        )

    return items
