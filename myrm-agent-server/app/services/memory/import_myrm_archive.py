"""Myrm archive memory import adapter.

[INPUT]
Myrm memory archive export with manifest + data sections.

[OUTPUT]
MemoryImportDryRunResult mapping archive data to native memory buckets.

[POS]
Myrm archive dry-run adapter extracted from import_adapters.py for single-responsibility.
"""

from __future__ import annotations

from myrm_agent_harness.toolkits.memory import (
    MemoryImportDryRunResult,
    MemoryImportMappingItem,
)

from app.services.memory.import_adapter_utils import (
    WARNING_MYRM_ARCHIVE_MEMORY_SECTION_MISSING,
    WARNING_MYRM_ARCHIVE_REVIEW_ONLY_SECTIONS,
    archive_item_count,
    build_result,
    object_dict,
)
from app.services.memory.import_native_json import dry_run_native_json

ARCHIVE_REVIEW_ONLY_SECTIONS = ("shared_context", "conversation", "replay", "audit")


def is_myrm_archive(payload: dict[str, object]) -> bool:
    """Detect whether the payload is a Myrm memory archive."""

    manifest = payload.get("manifest")
    return isinstance(manifest, dict) and manifest.get("format") == "myrm_memory_archive"


def dry_run_myrm_archive(payload: dict[str, object]) -> MemoryImportDryRunResult:
    """Map a Myrm archive export into native memory buckets without persisting."""

    manifest = object_dict(payload.get("manifest"))
    data = object_dict(payload.get("data"))
    memory_payload = data.get("memory")
    version = str(manifest.get("version") or payload.get("version") or "1")
    warnings: list[str] = []
    review_only_mappings: list[MemoryImportMappingItem] = []
    review_only_items = 0

    for section in ARCHIVE_REVIEW_ONLY_SECTIONS:
        item_count = archive_item_count(data.get(section))
        if item_count <= 0:
            continue
        review_only_items += item_count
        review_only_mappings.append(
            MemoryImportMappingItem(
                source_bucket=f"archive.{section}",
                status="unsupported",
                item_count=item_count,
                unmapped_count=item_count,
                reason="Archive section is restorable through /memory/archive/restore; this memory import path only writes native memory buckets.",
            )
        )

    if review_only_items > 0:
        warnings.append(WARNING_MYRM_ARCHIVE_REVIEW_ONLY_SECTIONS)
    if not isinstance(memory_payload, dict):
        warnings.append(WARNING_MYRM_ARCHIVE_MEMORY_SECTION_MISSING)
        return build_result(
            source="myrm_archive",
            version=version,
            normalized={},
            mappings=review_only_mappings,
            mapped_items=0,
            unmapped_items=review_only_items,
            warnings=warnings,
        )

    native_result = dry_run_native_json({"version": version, "data": object_dict(memory_payload)})
    return build_result(
        source="myrm_archive",
        version=version,
        normalized=native_result.normalized_data,
        mappings=native_result.mappings + review_only_mappings,
        mapped_items=native_result.summary.mapped_items,
        unmapped_items=native_result.summary.unmapped_items + review_only_items,
        warnings=native_result.warnings + warnings,
    )
