"""Shared utilities for memory import adapters.

[INPUT]
Raw dicts and values from external memory payloads.

[OUTPUT]
Normalized helper functions: type coercion, result builders, warning constants.

[POS]
Common utility layer shared by all import adapters (native, agentmemory, claude, hermes, etc.).
"""

from __future__ import annotations

from datetime import UTC, datetime

from myrm_agent_harness.toolkits.memory import (
    MemoryImportDryRunResult,
    MemoryImportDryRunSummary,
    MemoryImportMappingItem,
    MemoryImportSource,
    MemoryReliabilityStatus,
)

SUPPORTED_NATIVE_BUCKETS = {"profile", "semantic", "episodic", "procedural"}

WARNING_NO_NATIVE_BUCKETS = "no_native_buckets"
WARNING_MYRM_ARCHIVE_MEMORY_SECTION_MISSING = "myrm_archive_memory_section_missing"
WARNING_MYRM_ARCHIVE_REVIEW_ONLY_SECTIONS = "myrm_archive_non_memory_sections_review_only"
WARNING_AGENTMEMORY_VERSION_UNSUPPORTED = "agentmemory_version_unsupported"
WARNING_AGENTMEMORY_TOO_MANY_SESSIONS = "agentmemory_too_many_sessions"
WARNING_AGENTMEMORY_TOO_MANY_MEMORIES = "agentmemory_too_many_memories"
WARNING_AGENTMEMORY_TOO_MANY_SUMMARIES = "agentmemory_too_many_summaries"
WARNING_AGENTMEMORY_TOO_MANY_OBSERVATIONS = "agentmemory_too_many_observations"
WARNING_GRAPH_SKIPPED = "agentmemory_graph_skipped"
WARNING_ACCESS_LOGS_SKIPPED = "agentmemory_access_logs_skipped"
WARNING_UNSUPPORTED_SOURCE = "unsupported_source"
WARNING_CLAUDE_CODE_NO_LINES = "claude_code_no_lines"


def build_result(
    *,
    source: MemoryImportSource,
    version: str,
    normalized: dict[str, list[dict[str, object]]],
    mappings: list[MemoryImportMappingItem],
    mapped_items: int,
    unmapped_items: int,
    warnings: list[str],
) -> MemoryImportDryRunResult:
    """Build a standard dry-run result."""

    total_items = mapped_items + unmapped_items
    return MemoryImportDryRunResult(
        summary=MemoryImportDryRunSummary(
            source=source,
            version=version,
            total_items=total_items,
            mapped_items=mapped_items,
            unmapped_items=unmapped_items,
            status=_import_status(total_items, mapped_items, unmapped_items),
        ),
        mappings=mappings,
        warnings=warnings,
        normalized_data=normalized,
    )


def unsupported_result(source: MemoryImportSource, warning_code: str) -> MemoryImportDryRunResult:
    """Build a result for unsupported or unrecognized sources."""

    return MemoryImportDryRunResult(
        summary=MemoryImportDryRunSummary(source=source, total_items=0, mapped_items=0, unmapped_items=0, status="missing"),
        mappings=[MemoryImportMappingItem(source_bucket=source, status="unsupported", reason=warning_code)],
        warnings=[warning_code],
    )


def object_dict(value: object) -> dict[str, object]:
    """Safely coerce a value to a string-keyed dict."""

    if not isinstance(value, dict):
        return {}
    return {str(key): nested for key, nested in value.items()}


def to_list(value: object) -> list[object]:
    """Safely coerce a value to a list."""

    return list(value) if isinstance(value, list) else []


def archive_item_count(value: object) -> int:
    """Recursively count items in an archive section."""

    if isinstance(value, list):
        return len(value)
    if isinstance(value, dict):
        return sum(archive_item_count(item) for item in value.values())
    return 0


def text(value: object) -> str:
    """Extract a stripped string or return empty."""

    return value.strip() if isinstance(value, str) else ""


def string_list(value: object) -> list[str]:
    """Extract a list of non-empty stripped strings."""

    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def float_between(value: object, fallback: float) -> float:
    """Clamp a numeric value to [0, 1] or return fallback."""

    if isinstance(value, int | float):
        return min(max(float(value), 0.0), 1.0)
    return fallback


def strength_to_score(value: object) -> float:
    """Convert agentmemory-style 0-10 strength to 0-1 score."""

    if isinstance(value, int | float):
        return min(max(float(value) / 10.0, 0.0), 1.0)
    return 0.7


def iso_or_now(value: object) -> str:
    """Return ISO string or current UTC timestamp."""

    if isinstance(value, str) and value:
        return value
    return datetime.now(UTC).isoformat()


def build_metadata(source: str, item: dict[str, object], fields: tuple[str, ...]) -> dict[str, str | int | float | bool]:
    """Build metadata dict from selected fields of an imported item."""

    metadata: dict[str, str | int | float | bool] = {"external_source": source}
    for field in fields:
        value = item.get(field)
        if isinstance(value, str | int | float | bool):
            metadata[f"external_{field}"] = value
        elif isinstance(value, list):
            metadata[f"external_{field}"] = ",".join(str(entry) for entry in value if isinstance(entry, str | int | float | bool))
    return metadata


def to_memory_import_source(source: str) -> MemoryImportSource:
    """Map a raw source string to a typed MemoryImportSource literal."""

    _KNOWN: set[str] = {
        "native_json", "myrm_archive", "agentmemory", "gbrain", "memweaver",
        "claude_code_jsonl", "hermes", "openclaw", "cursor_rules", "codex", "claude",
    }
    if source in _KNOWN:
        return source  # type: ignore[return-value]
    return "unknown"


def _import_status(total_items: int, mapped_items: int, unmapped_items: int) -> MemoryReliabilityStatus:
    if total_items == 0:
        return "missing"
    if mapped_items == total_items:
        return "ready"
    if mapped_items > 0 and unmapped_items > 0:
        return "warning"
    return "critical"
