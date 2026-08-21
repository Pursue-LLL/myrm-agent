"""PLUR engram memory import adapter.

[INPUT]
PLUR engram data payload containing structured memory engrams.
Expected payload structures:
  - ``plur_engrams``: list[dict] — raw engram records with domain/scope/content/timestamp/type
  - ``raw_yaml``: str — plain YAML content from ~/.plur/ or .plur.yaml
  - ``engrams``: list[dict] — simplified engram objects
  - ``_source``: "plur" — source identifier

[OUTPUT]
MemoryImportDryRunResult mapping PLUR engrams to native semantic and profile buckets.

[POS]
PLUR competitor import adapter. Converts PLUR's local YAML engram format
into native MyrmAgent memory format, cleanly mapping scopes to SharedContext or personal profile.
"""

from __future__ import annotations

from typing import Any

import yaml
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


def dry_run_plur(payload: dict[str, object]) -> MemoryImportDryRunResult:
    """Map a PLUR engram data payload into native memory buckets without persisting."""

    normalized: dict[str, list[dict[str, object]]] = {}
    mappings: list[MemoryImportMappingItem] = []
    warnings: list[str] = []
    mapped_items = 0
    unmapped_items = 0

    raw_engrams = _extract_engrams(payload)

    if not raw_engrams:
        return build_result(
            source="plur",
            version="1",
            normalized=normalized,
            mappings=[
                MemoryImportMappingItem(
                    source_bucket="plur_engrams",
                    target_bucket="semantic",
                    status="unsupported",
                    item_count=0,
                    imported_count=0,
                    reason="No valid PLUR engrams found in payload.",
                )
            ],
            mapped_items=0,
            unmapped_items=0,
            warnings=["plur_no_engrams_found"],
        )

    semantic_items: list[dict[str, object]] = []
    profile_items: list[dict[str, object]] = []

    for entry in raw_engrams:
        if not isinstance(entry, dict):
            unmapped_items += 1
            continue

        content = text(entry.get("content") or entry.get("text") or entry.get("summary"))
        if not content:
            unmapped_items += 1
            continue

        domain = text(entry.get("domain") or "general")
        scope = text(entry.get("scope") or "global")
        domain = text(entry.get("domain") or "default")
        engram_type = text(entry.get("type") or entry.get("category") or "fact")
        created_at = iso_or_now(entry.get("timestamp") or entry.get("created_at"))

        meta = build_metadata(
            "plur",
            entry,
            ("domain", "scope", "type", "id"),
        )

        item: dict[str, object] = {
            "content": content,
            "key": f"plur_{domain}_{engram_type}",
            "value": content,
            "created_at": created_at,
            "metadata": meta,
        }

        if scope == "global" and engram_type in {"preference", "user_rule", "profile"}:
            profile_items.append(item)
        else:
            semantic_items.append(item)

    if semantic_items:
        normalized["semantic"] = semantic_items
        mapped_items += len(semantic_items)
        mappings.append(
            MemoryImportMappingItem(
                source_bucket="plur_engrams",
                target_bucket="semantic",
                status="mapped",
                item_count=len(semantic_items),
                imported_count=len(semantic_items),
                reason="",
            )
        )

    if profile_items:
        normalized["profile"] = profile_items
        mapped_items += len(profile_items)
        mappings.append(
            MemoryImportMappingItem(
                source_bucket="plur_preferences",
                target_bucket="profile",
                status="mapped",
                item_count=len(profile_items),
                imported_count=len(profile_items),
                reason="",
            )
        )

    return build_result(
        source="plur",
        version="1",
        normalized=normalized,
        mappings=mappings,
        mapped_items=mapped_items,
        unmapped_items=unmapped_items,
        warnings=warnings,
    )


def is_plur_payload(payload: dict[str, object]) -> bool:
    """Detect whether the payload is from PLUR engram source."""

    if str(payload.get("_source", "")).strip().lower() == "plur":
        return True
    if "plur_engrams" in payload or "engrams" in payload:
        return True
    raw_yaml = payload.get("raw_yaml")
    if isinstance(raw_yaml, str) and ("domain:" in raw_yaml or "engrams:" in raw_yaml):
        return True
    return False


def _extract_engrams(payload: dict[str, object]) -> list[dict[str, object]]:
    """Safely extract list of engram dictionaries from JSON or YAML payload."""

    if isinstance(payload.get("plur_engrams"), list):
        return [object_dict(item) for item in payload["plur_engrams"] if isinstance(item, dict)]

    if isinstance(payload.get("engrams"), list):
        return [object_dict(item) for item in payload["engrams"] if isinstance(item, dict)]

    raw_yaml = payload.get("raw_yaml")
    if isinstance(raw_yaml, str) and raw_yaml.strip():
        try:
            parsed: Any = yaml.safe_load(raw_yaml)
            if isinstance(parsed, list):
                return [object_dict(item) for item in parsed if isinstance(item, dict)]
            if isinstance(parsed, dict):
                if isinstance(parsed.get("engrams"), list):
                    return [object_dict(item) for item in parsed["engrams"] if isinstance(item, dict)]
                return [object_dict(parsed)]
        except Exception:
            return []

    return []
