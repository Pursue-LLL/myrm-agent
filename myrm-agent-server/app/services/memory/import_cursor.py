"""Cursor rules/settings memory import adapter.

[INPUT]
Cursor data payload with rules and settings extracted from .cursor/ directories.

Expected payload keys (populated by competitor_discovery or frontend upload):
  - ``cursor_rules``: list[dict] — rule definitions from .cursor/rules/
  - ``cursor_settings``: dict — settings.json content
  - ``_source``: "cursor_rules" — source identifier

[OUTPUT]
MemoryImportDryRunResult mapping Cursor data to native procedural/profile buckets.

[POS]
Cursor competitor import adapter. Converts Cursor rules (coding conventions,
project guidelines) into procedural memories and settings into profile memories.
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


def dry_run_cursor(payload: dict[str, object]) -> MemoryImportDryRunResult:
    """Map a Cursor data payload into native memory buckets without persisting."""

    normalized: dict[str, list[dict[str, object]]] = {}
    mappings: list[MemoryImportMappingItem] = []
    warnings: list[str] = []
    mapped_items = 0
    unmapped_items = 0

    rules = payload.get("cursor_rules")
    if isinstance(rules, list) and rules:
        procedural_items = _parse_rules(rules)
        if procedural_items:
            normalized["procedural"] = procedural_items
            mapped_items += len(procedural_items)
        mappings.append(MemoryImportMappingItem(
            source_bucket="cursor_rules",
            target_bucket="procedural",
            status="mapped" if procedural_items else "unsupported",
            item_count=len(rules),
            imported_count=len(procedural_items),
            reason="" if procedural_items else "No valid rules found.",
        ))

    settings = payload.get("cursor_settings")
    if isinstance(settings, dict) and settings:
        profile_items = _parse_settings(settings)
        if profile_items:
            normalized.setdefault("profile", []).extend(profile_items)
            mapped_items += len(profile_items)
        mappings.append(MemoryImportMappingItem(
            source_bucket="cursor_settings",
            target_bucket="profile",
            status="mapped" if profile_items else "unsupported",
            item_count=1,
            imported_count=len(profile_items),
            reason="" if profile_items else "No importable settings found.",
        ))

    if not normalized:
        unmapped_items += 1
        warnings.append("cursor_empty_payload")

    return build_result(
        source="cursor_rules",
        version="1",
        normalized=normalized,
        mappings=mappings,
        mapped_items=mapped_items,
        unmapped_items=unmapped_items,
        warnings=warnings,
    )


def _parse_rules(rules: list[object]) -> list[dict[str, object]]:
    """Convert Cursor rules to procedural memory items."""

    items: list[dict[str, object]] = []
    for raw_rule in rules:
        if not isinstance(raw_rule, dict):
            continue
        rule = object_dict(raw_rule)
        content = text(rule.get("content")) or text(rule.get("body"))
        name = text(rule.get("name")) or text(rule.get("title")) or "Cursor rule"
        if not content:
            continue

        items.append({
            "content": f"{name}\n{content}".strip() if name != "Cursor rule" else content,
            "trigger": f"When working on project: {name}",
            "action": content[:500],
            "priority": 7,
            "trigger_keywords": [tag for tag in [text(rule.get("globs")), "cursor_rule"] if tag],
            "created_at": iso_or_now(rule.get("created_at")),
            "metadata": build_metadata("cursor", rule, ("name", "globs", "alwaysApply")),
        })
    return items


def _parse_settings(settings: object) -> list[dict[str, object]]:
    """Extract meaningful preferences from Cursor settings as profile memories."""

    if not isinstance(settings, dict):
        return []
    typed = object_dict(settings)
    items: list[dict[str, object]] = []

    preferred_language = text(typed.get("preferredLanguage"))
    if preferred_language:
        items.append({
            "content": f"Preferred programming language: {preferred_language}",
            "memory_type": "profile",
            "importance": 0.7,
            "confidence": 0.9,
            "tags": ["cursor_preference", "language"],
            "created_at": iso_or_now(None),
            "metadata": build_metadata("cursor", typed, ("preferredLanguage",)),
        })

    theme = text(typed.get("theme")) or text(typed.get("workbench.colorTheme"))
    if theme:
        items.append({
            "content": f"Preferred editor theme: {theme}",
            "memory_type": "profile",
            "importance": 0.3,
            "confidence": 0.9,
            "tags": ["cursor_preference", "theme"],
            "created_at": iso_or_now(None),
            "metadata": build_metadata("cursor", {"theme": theme}, ("theme",)),
        })

    return items
