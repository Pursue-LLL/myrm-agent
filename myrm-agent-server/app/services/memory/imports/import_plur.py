"""PLUR engram import adapter (Open Engram Standard v1).

[INPUT]
PLUR payload with either ``engrams`` (a parsed store file) or ``raw_yaml``
(the canonical ``~/.plur/engrams.yaml`` text). Engram fields follow the Open
Engram Standard: ``id`` / ``statement`` / ``type`` / ``status`` / ``scope`` /
``visibility`` / ``domain`` / ``created_at``.

[OUTPUT]
MemoryImportDryRunResult mapping active engrams into procedural and semantic
buckets; inactive lifecycle states are skipped with explicit reasons.

[POS]
PLUR competitor import adapter. Reads the official store format (statement is
the load-bearing text), never synthesizes missing timestamps, and keeps engram
provenance fields in metadata so the imported memory stays auditable.
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

ACTIVE_STATUS = "active"
PROCEDURAL_TYPES = frozenset({"procedural", "behavioral"})

WARNING_NO_ENGRAMS = "plur_no_engrams_found"
WARNING_INACTIVE_SKIPPED = "plur_inactive_skipped"
WARNING_INVALID_ENGRAMS = "plur_invalid_engrams"


def dry_run_plur(payload: dict[str, object]) -> MemoryImportDryRunResult:
    """Map a PLUR engram payload into native memory buckets without persisting."""

    raw_engrams = _extract_engrams(payload)
    if not raw_engrams:
        return build_result(
            source="plur",
            version="1",
            normalized={},
            mappings=[
                MemoryImportMappingItem(
                    source_bucket="engrams",
                    target_bucket="semantic",
                    status="unsupported",
                    item_count=0,
                    reason="No PLUR engrams found in payload (expected engrams.yaml content).",
                ),
            ],
            mapped_items=0,
            unmapped_items=0,
            warnings=[WARNING_NO_ENGRAMS],
        )

    normalized: dict[str, list[dict[str, object]]] = {}
    mapped_by_bucket = {bucket: 0 for bucket in ("procedural", "semantic")}
    inactive_skipped = 0
    invalid_skipped = 0

    for raw_entry in raw_engrams:
        entry = object_dict(raw_entry)
        statement = text(entry.get("statement"))
        if not statement:
            invalid_skipped += 1
            continue
        status = text(entry.get("status")) or ACTIVE_STATUS
        if status != ACTIVE_STATUS:
            inactive_skipped += 1
            continue
        bucket = _bucket_for_engram(entry)
        normalized.setdefault(bucket, []).append(_engram_item(entry, statement, bucket))
        mapped_by_bucket[bucket] += 1

    mapped_items = sum(mapped_by_bucket.values())
    mappings: list[MemoryImportMappingItem] = []
    for bucket in ("procedural", "semantic"):
        bucket_items = normalized.get(bucket, [])
        if not bucket_items:
            continue
        mappings.append(
            MemoryImportMappingItem(
                source_bucket="engrams",
                target_bucket=bucket,
                status="mapped",
                item_count=len(bucket_items),
                imported_count=len(bucket_items),
            ),
        )
    skipped_total = inactive_skipped + invalid_skipped
    if skipped_total:
        mappings.append(
            MemoryImportMappingItem(
                source_bucket="engrams",
                status="dropped",
                item_count=skipped_total,
                unmapped_count=skipped_total,
                reason=(
                    "Engrams with a non-active lifecycle status are not imported"
                    if not invalid_skipped
                    else "Engrams without a statement or with a non-active lifecycle status are not imported"
                ),
            ),
        )

    warnings: list[str] = []
    if inactive_skipped:
        warnings.append(WARNING_INACTIVE_SKIPPED)
    if invalid_skipped:
        warnings.append(WARNING_INVALID_ENGRAMS)

    return build_result(
        source="plur",
        version="1",
        normalized=normalized,
        mappings=mappings,
        mapped_items=mapped_items,
        unmapped_items=skipped_total,
        warnings=warnings,
    )


def is_plur_payload(payload: dict[str, object]) -> bool:
    """Detect PLUR data: official engram store shape or explicit source tag."""

    if str(payload.get("_source", "")).strip().lower() == "plur":
        return True
    engrams = payload.get("engrams")
    if isinstance(engrams, list):
        for entry in engrams[:5]:
            if isinstance(entry, dict) and "statement" in entry:
                return True
    raw_yaml = payload.get("raw_yaml")
    if isinstance(raw_yaml, str) and "engrams:" in raw_yaml and "statement:" in raw_yaml:
        return True
    return False


def _extract_engrams(payload: dict[str, object]) -> list[object]:
    """Extract engram dicts from parsed payloads or the raw store YAML."""

    engrams = payload.get("engrams")
    if isinstance(engrams, list):
        return [entry for entry in engrams if isinstance(entry, dict)]

    raw_yaml = payload.get("raw_yaml")
    if isinstance(raw_yaml, str) and raw_yaml.strip():
        try:
            parsed: Any = yaml.safe_load(raw_yaml)
        except yaml.YAMLError:
            return []
        if isinstance(parsed, dict):
            parsed_engrams = parsed.get("engrams")
            if isinstance(parsed_engrams, list):
                return [entry for entry in parsed_engrams if isinstance(entry, dict)]
    return []


def _bucket_for_engram(entry: dict[str, object]) -> str:
    """Map a PLUR knowledge class onto a native memory bucket."""

    engram_type = text(entry.get("type")).strip().lower()
    return "procedural" if engram_type in PROCEDURAL_TYPES else "semantic"


def _engram_item(entry: dict[str, object], statement: str, bucket: str) -> dict[str, object]:
    """Build the native bucket item for one active engram."""

    engram_type = text(entry.get("type")).strip().lower()
    domain = text(entry.get("domain"))
    tags = ["plur"]
    if domain:
        tags.append(domain)
    if engram_type:
        tags.append(engram_type)
    metadata = build_metadata(
        "plur",
        {
            "id": text(entry.get("id")),
            "type": engram_type,
            "scope": text(entry.get("scope")),
            "status": text(entry.get("status")) or ACTIVE_STATUS,
            "domain": domain,
            "polarity": text(entry.get("polarity")),
            "commitment": text(entry.get("commitment")),
        },
        ("id", "type", "scope", "status", "domain", "polarity", "commitment"),
    )
    created_at = iso_or_now(entry.get("created_at"))
    if bucket == "procedural":
        return {
            "content": statement,
            "priority": 5,
            "trigger_keywords": ["plur"],
            "tags": tags,
            "created_at": created_at,
            "metadata": metadata,
        }
    return {
        "content": statement,
        "importance": 0.7,
        "confidence": 0.75,
        "tags": tags,
        "created_at": created_at,
        "metadata": metadata,
    }
