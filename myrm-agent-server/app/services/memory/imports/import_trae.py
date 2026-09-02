"""TRAE memory import adapter.

[INPUT]
TRAE data payload with project/user rules and settings.

Expected payload keys (populated by frontend upload from .trae/rules/):
  - ``trae_rules``: list[dict] — rule definitions (project_rules.md / user_rules.md)
  - ``trae_settings``: dict — TRAE configuration
  - ``_source``: "trae" — source identifier

[OUTPUT]
MemoryImportDryRunResult mapping TRAE data to native procedural/profile buckets.

[POS]
TRAE competitor import adapter. Converts TRAE project and user rules
(coding conventions, project guidelines) into procedural memories and
settings into profile memories. Memory Center manual-import lane only;
Wizard filesystem discovery stays a closed 5-source set (see
services/migration/_ARCH.md).
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
    object_dict,
    text,
)


def dry_run_trae(payload: dict[str, object]) -> MemoryImportDryRunResult:
    """Map a TRAE data payload into native memory buckets without persisting."""

    normalized: dict[str, list[dict[str, object]]] = {}
    mappings: list[MemoryImportMappingItem] = []
    warnings: list[str] = []
    mapped_items = 0
    unmapped_items = 0

    rules = payload.get("trae_rules")
    if isinstance(rules, list) and rules:
        procedural_items = _parse_rules(rules)
        if procedural_items:
            normalized["procedural"] = procedural_items
            mapped_items += len(procedural_items)
        mappings.append(
            MemoryImportMappingItem(
                source_bucket="trae_rules",
                target_bucket="procedural",
                status="mapped" if procedural_items else "unsupported",
                item_count=len(rules),
                imported_count=len(procedural_items),
                reason="" if procedural_items else "No valid rules found.",
            )
        )

    settings = payload.get("trae_settings")
    if isinstance(settings, dict) and settings:
        profile_items = _parse_settings(settings)
        if profile_items:
            normalized.setdefault("profile", []).extend(profile_items)
            mapped_items += len(profile_items)
        mappings.append(
            MemoryImportMappingItem(
                source_bucket="trae_settings",
                target_bucket="profile",
                status="mapped" if profile_items else "unsupported",
                item_count=1,
                imported_count=len(profile_items),
                reason="" if profile_items else "No importable settings found.",
            )
        )

    if not normalized:
        unmapped_items += 1
        warnings.append("trae_empty_payload")

    return build_result(
        source="trae",
        version="1",
        normalized=normalized,
        mappings=mappings,
        mapped_items=mapped_items,
        unmapped_items=unmapped_items,
        warnings=warnings,
    )


def _parse_rules(rules: list[object]) -> list[dict[str, object]]:
    """Convert TRAE rules to procedural memory items."""

    items: list[dict[str, object]] = []
    for raw_rule in rules:
        if not isinstance(raw_rule, dict):
            continue
        rule = object_dict(raw_rule)
        content = text(rule.get("content")) or text(rule.get("body"))
        name = text(rule.get("name")) or text(rule.get("title")) or "TRAE rule"
        scope = text(rule.get("scope")) or ("project" if text(rule.get("source")) == "project_rules" else "")
        if not content:
            continue

        items.append(
            {
                "content": (f"{name}\n{content}".strip() if name != "TRAE rule" else content),
                "trigger": (f"When working on project: {name}" if scope != "user" else "When working on any project"),
                "action": content[:500],
                "priority": 7,
                "trigger_keywords": [tag for tag in [scope or None, "trae_rule"] if tag],
                "created_at": iso_or_now(rule.get("created_at")),
                "metadata": build_metadata("trae", rule, ("name", "scope", "source")),
            }
        )
    return items


def _parse_settings(settings: object) -> list[dict[str, object]]:
    """Extract meaningful preferences from TRAE settings as profile memories."""

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
                "tags": ["trae_preference", "language"],
                "created_at": iso_or_now(None),
                "metadata": build_metadata("trae", typed, ("preferredLanguage",)),
            }
        )

    return items
