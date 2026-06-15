"""Codex memory import adapter.

[INPUT]
Codex data payload with instructions and settings.

Expected payload keys (populated by source_discovery or frontend upload):
  - ``codex_instructions``: str — AGENTS.md / instructions content
  - ``codex_settings``: dict — Codex configuration
  - ``codex_memory``: list[dict] — memory entries if available
  - ``_source``: "codex" — source identifier

[OUTPUT]
MemoryImportDryRunResult mapping Codex data to native procedural/semantic buckets.

[POS]
Codex competitor import adapter. Converts Codex instructions and settings
into procedural and semantic memories.
"""

from __future__ import annotations

from myrm_agent_harness.toolkits.memory import (
    MemoryImportDryRunResult,
    MemoryImportMappingItem,
)

from app.services.memory.import_adapter_utils import (
    build_metadata,
    build_result,
    iso_or_now,
    object_dict,
    text,
)


def dry_run_codex(payload: dict[str, object]) -> MemoryImportDryRunResult:
    """Map a Codex data payload into native memory buckets without persisting."""

    normalized: dict[str, list[dict[str, object]]] = {}
    mappings: list[MemoryImportMappingItem] = []
    warnings: list[str] = []
    mapped_items = 0
    unmapped_items = 0

    instructions = payload.get("codex_instructions")
    if isinstance(instructions, str) and instructions.strip():
        procedural_items = _parse_instructions(instructions.strip())
        if procedural_items:
            normalized["procedural"] = procedural_items
            mapped_items += len(procedural_items)
        mappings.append(
            MemoryImportMappingItem(
                source_bucket="codex_instructions",
                target_bucket="procedural",
                status="mapped" if procedural_items else "unsupported",
                item_count=1,
                imported_count=len(procedural_items),
                reason="" if procedural_items else "Instructions were empty.",
            )
        )

    memory_entries = payload.get("codex_memory")
    if isinstance(memory_entries, list) and memory_entries:
        semantic_items = _parse_memory(memory_entries)
        if semantic_items:
            normalized.setdefault("semantic", []).extend(semantic_items)
            mapped_items += len(semantic_items)
        mappings.append(
            MemoryImportMappingItem(
                source_bucket="codex_memory",
                target_bucket="semantic",
                status="mapped" if semantic_items else "unsupported",
                item_count=len(memory_entries),
                imported_count=len(semantic_items),
                reason="" if semantic_items else "No valid memory entries found.",
            )
        )

    settings = payload.get("codex_settings")
    if isinstance(settings, dict) and settings:
        profile_items = _parse_settings(settings)
        if profile_items:
            normalized.setdefault("profile", []).extend(profile_items)
            mapped_items += len(profile_items)
        mappings.append(
            MemoryImportMappingItem(
                source_bucket="codex_settings",
                target_bucket="profile",
                status="mapped" if profile_items else "unsupported",
                item_count=1,
                imported_count=len(profile_items),
            )
        )

    if not normalized:
        unmapped_items += 1
        warnings.append("codex_empty_payload")

    return build_result(
        source="codex",
        version="1",
        normalized=normalized,
        mappings=mappings,
        mapped_items=mapped_items,
        unmapped_items=unmapped_items,
        warnings=warnings,
    )


def _parse_instructions(content: str) -> list[dict[str, object]]:
    """Convert Codex instructions into a procedural memory item."""

    if not content:
        return []
    return [
        {
            "content": content,
            "trigger": "When working on Codex-originated project",
            "action": content[:500],
            "priority": 7,
            "trigger_keywords": ["codex_instructions"],
            "created_at": iso_or_now(None),
            "metadata": build_metadata("codex", {"file": "instructions"}, ("file",)),
        }
    ]


def _parse_memory(entries: list[object]) -> list[dict[str, object]]:
    """Convert Codex memory entries into semantic memory items."""

    items: list[dict[str, object]] = []
    for raw_entry in entries:
        if not isinstance(raw_entry, dict):
            continue
        entry = object_dict(raw_entry)
        content = text(entry.get("content")) or text(entry.get("text"))
        if not content:
            continue
        items.append(
            {
                "content": content,
                "importance": 0.7,
                "confidence": 0.75,
                "tags": ["codex_memory"],
                "created_at": iso_or_now(entry.get("created_at") or entry.get("timestamp")),
                "metadata": build_metadata("codex", entry, ("id", "type")),
            }
        )
    return items


def _parse_settings(settings: object) -> list[dict[str, object]]:
    """Extract preferences from Codex settings as profile memories."""

    if not isinstance(settings, dict):
        return []
    typed = object_dict(settings)
    model = text(typed.get("model"))
    if model:
        return [
            {
                "content": f"Previously used Codex with model: {model}",
                "memory_type": "profile",
                "importance": 0.4,
                "confidence": 0.9,
                "tags": ["codex_preference"],
                "created_at": iso_or_now(None),
                "metadata": build_metadata("codex", {"model": model}, ("model",)),
            }
        ]
    return []
