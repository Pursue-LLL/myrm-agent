"""Claude Code JSONL memory import adapter.

[INPUT]
Claude Code transcript payload with ``jsonl_lines`` key.

[OUTPUT]
MemoryImportDryRunResult mapping Claude Code conversation data to native buckets.

[POS]
Claude Code JSONL dry-run adapter extracted from import_adapters.py for single-responsibility.
"""

from __future__ import annotations

from myrm_agent_harness.toolkits.memory import (
    MemoryImportDryRunResult,
    MemoryImportMappingItem,
)

from app.services.memory.import_adapter_utils import (
    WARNING_CLAUDE_CODE_NO_LINES,
    build_result,
    unsupported_result,
)


def is_claude_code_jsonl(payload: dict[str, object]) -> bool:
    """Detect Claude Code JSONL by checking for ``jsonl_lines`` key with typical entry shapes."""

    lines = payload.get("jsonl_lines")
    if not isinstance(lines, list) or len(lines) == 0:
        return False
    sample = lines[0]
    if not isinstance(sample, dict):
        return False
    return isinstance(sample.get("type"), str) and sample.get("type") in {
        "user",
        "assistant",
        "system",
        "summary",
    }


def dry_run_claude_code_jsonl(payload: dict[str, object]) -> MemoryImportDryRunResult:
    """Map a Claude Code JSONL transcript into native memory buckets without persisting."""

    from .import_claude_code_parser import (
        errors_to_procedural,
        parse_claude_code_lines,
        summaries_to_semantic,
        turns_to_episodic,
    )

    lines = payload.get("jsonl_lines")
    if not isinstance(lines, list) or len(lines) == 0:
        return unsupported_result("claude_code_jsonl", WARNING_CLAUDE_CODE_NO_LINES)

    parsed = parse_claude_code_lines(lines)

    episodic = turns_to_episodic(parsed.turns)
    semantic = summaries_to_semantic(parsed.summaries)
    procedural = errors_to_procedural(parsed.errors)

    normalized: dict[str, list[dict[str, object]]] = {}
    if episodic:
        normalized["episodic"] = episodic
    if semantic:
        normalized["semantic"] = semantic
    if procedural:
        normalized["procedural"] = procedural

    mappings: list[MemoryImportMappingItem] = [
        MemoryImportMappingItem(
            source_bucket="conversation_turns",
            target_bucket="episodic",
            status="mapped" if episodic else "unsupported",
            item_count=parsed.user_entries,
            imported_count=len(episodic),
            reason="" if episodic else "No conversation turns extracted.",
        ),
        MemoryImportMappingItem(
            source_bucket="summaries",
            target_bucket="semantic",
            status="mapped" if semantic else "unsupported",
            item_count=parsed.summary_entries,
            imported_count=len(semantic),
            reason="" if semantic else "No summaries found in transcript.",
        ),
        MemoryImportMappingItem(
            source_bucket="system_errors",
            target_bucket="procedural",
            status="mapped" if procedural else "unsupported",
            item_count=parsed.system_entries,
            imported_count=len(procedural),
            reason="" if procedural else "No error patterns found.",
        ),
    ]

    mapped_items = len(episodic) + len(semantic) + len(procedural)
    total_entries = parsed.deduplicated_entries
    unmapped_items = max(total_entries - mapped_items, 0)

    return build_result(
        source="claude_code_jsonl",
        version="1",
        normalized=normalized,
        mappings=mappings,
        mapped_items=mapped_items,
        unmapped_items=unmapped_items,
        warnings=parsed.warnings,
    )
