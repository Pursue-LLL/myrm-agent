"""gbrain memory import adapter.

[INPUT]
gbrain export payload with parsed pages (type, title, compiled_truth, timeline, tags, frontmatter).

Expected payload keys:
  - ``gbrain_pages``: list[dict] — parsed gbrain pages with type/title/compiled_truth/timeline/tags
  - ``_source``: "gbrain" — source identifier

[OUTPUT]
MemoryImportDryRunResult mapping gbrain pages to native semantic/profile/episodic buckets.

[POS]
gbrain competitor import adapter. Maps gbrain page types (person, concept, meeting, etc.)
into native memory buckets for the dry-run → confirm → rollback pipeline.
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

_PROFILE_TYPES = frozenset({"person", "company", "deal", "yc", "civic"})
_EPISODIC_TYPES = frozenset({
    "meeting", "email", "slack", "calendar-event", "conversation",
    "event", "diary",
})
_SEMANTIC_TYPES = frozenset({
    "concept", "source", "media", "writing", "analysis", "guide",
    "hardware", "architecture", "project", "note", "code", "image",
    "synthesis", "atom", "extract_receipt",
})


def _classify_page_type(page_type: str) -> str:
    """Map a gbrain page type to a Myrm memory bucket."""

    lower = page_type.lower().strip()
    if lower in _PROFILE_TYPES:
        return "profile"
    if lower in _EPISODIC_TYPES:
        return "episodic"
    if lower in _SEMANTIC_TYPES:
        return "semantic"
    return "semantic"


def dry_run_gbrain(payload: dict[str, object]) -> MemoryImportDryRunResult:
    """Map a gbrain data payload into native memory buckets without persisting."""

    normalized: dict[str, list[dict[str, object]]] = {}
    mappings: list[MemoryImportMappingItem] = []
    warnings: list[str] = []
    mapped_items = 0

    pages = payload.get("gbrain_pages")
    if not isinstance(pages, list) or not pages:
        return build_result(
            source="gbrain",
            version="1",
            normalized={},
            mappings=[MemoryImportMappingItem(
                source_bucket="gbrain_pages",
                status="unsupported",
                item_count=0,
                reason="No gbrain pages found in payload.",
            )],
            mapped_items=0,
            unmapped_items=0,
            warnings=["gbrain_no_pages"],
        )

    type_counts: dict[str, int] = {}
    for page in pages:
        if not isinstance(page, dict):
            continue
        page_type = str(page.get("type", "")).strip()
        if not page_type:
            continue

        bucket = _classify_page_type(page_type)
        compiled_truth = str(page.get("compiled_truth", "")).strip()
        timeline = str(page.get("timeline", "")).strip()
        title = str(page.get("title", "")).strip()
        tags_raw = page.get("tags")
        tags = [str(t) for t in tags_raw if isinstance(t, str)] if isinstance(tags_raw, list) else []
        frontmatter = page.get("frontmatter")
        emotional_weight = frontmatter.get("emotional_weight") if isinstance(frontmatter, dict) else None

        content = compiled_truth
        if timeline:
            content += f"\n\n---\n{timeline}"

        importance = 0.7
        if isinstance(emotional_weight, int | float):
            importance = min(max(float(emotional_weight), 0.0), 1.0)
        elif bucket == "profile":
            importance = 0.85

        item: dict[str, object] = {
            "content": f"[{title}] {content}" if title else content,
            "memory_type": bucket,
            "importance": importance,
            "confidence": 0.8,
            "tags": ["gbrain", f"gbrain_{page_type}"] + tags,
            "created_at": iso_or_now(None),
            "metadata": build_metadata("gbrain", {
                "type": page_type,
                "title": title,
                "slug": str(page.get("slug", "")),
            }, ("type", "title", "slug")),
        }

        normalized.setdefault(bucket, []).append(item)
        mapped_items += 1
        type_counts[page_type] = type_counts.get(page_type, 0) + 1

    for page_type, count in sorted(type_counts.items()):
        bucket = _classify_page_type(page_type)
        mappings.append(MemoryImportMappingItem(
            source_bucket=f"gbrain/{page_type}",
            target_bucket=bucket,
            status="mapped",
            item_count=count,
            imported_count=count,
        ))

    return build_result(
        source="gbrain",
        version="1",
        normalized=normalized,
        mappings=mappings,
        mapped_items=mapped_items,
        unmapped_items=0,
        warnings=warnings,
    )
