"""Memory import adapter dispatcher.

[INPUT]
External memory export payloads from various sources (native JSON, Myrm archives,
AgentMemory, Claude Code JSONL, Hermes, OpenClaw, Codex; Memory Center also
supports cursor_rules and mem0 outside the Wizard discover set).

[OUTPUT]
Content-safe dry-run mapping result and normalized memory import data.

[POS]
Single-user import adapter dispatch layer. Routes payloads to source-specific
adapters inside the local/Tauri/per-user sandbox server. Individual adapters
live in sibling ``import_*.py`` modules for single-responsibility compliance.
"""

from __future__ import annotations

from typing import Literal

from myrm_agent_harness.toolkits.memory import (
    MemoryImportDryRunResult,
    MemoryImportSource,
)

from app.services.memory.import_adapter_utils import (
    SUPPORTED_NATIVE_BUCKETS,
    WARNING_UNSUPPORTED_SOURCE,
    to_memory_import_source,
    unsupported_result,
)
from app.services.memory.import_agentmemory import dry_run_agentmemory
from app.services.memory.import_claude_code import dry_run_claude_code_jsonl, is_claude_code_jsonl
from app.services.memory.import_codex import dry_run_codex
from app.services.memory.import_cursor import dry_run_cursor
from app.services.memory.import_hermes import dry_run_hermes
from app.services.memory.import_mem0 import dry_run_mem0, is_mem0_payload
from app.services.memory.import_myrm_archive import dry_run_myrm_archive, is_myrm_archive
from app.services.memory.import_native_json import dry_run_native_json
from app.services.memory.import_openclaw import dry_run_openclaw
from app.services.migration.source_payload_loader import (
    is_source_discovery_payload,
    load_source_payload,
)

RequestedImportSource = Literal[
    "auto",
    "native_json",
    "myrm_archive",
    "agentmemory",
    "gbrain",
    "memweaver",
    "claude_code_jsonl",
    "hermes",
    "openclaw",
    "cursor_rules",
    "codex",
    "claude",
    "mem0",
]

_MIGRATION_SOURCE_TO_ADAPTER: dict[str, RequestedImportSource] = {
    "hermes": "hermes",
    "openclaw": "openclaw",
    "codex": "codex",
    "claude": "claude",
    "mem0": "mem0",
}

_SOURCE_TAG_TO_IMPORT: dict[str, MemoryImportSource] = {
    "hermes": "hermes",
    "openclaw": "openclaw",
    "cursor": "cursor_rules",
    "cursor_rules": "cursor_rules",
    "codex": "codex",
    "claude": "claude",
    "mem0": "mem0",
}


def resolve_migration_source(competitor: str) -> RequestedImportSource:
    """Map a source discovery id to the memory import adapter source."""

    return _MIGRATION_SOURCE_TO_ADAPTER.get(competitor.strip().lower(), "auto")


def build_memory_import_dry_run(
    payload: dict[str, object],
    source: RequestedImportSource = "auto",
) -> MemoryImportDryRunResult:
    """Map an import payload into native memory buckets without persisting it."""

    resolved_payload = payload
    resolved_source: RequestedImportSource = source
    if is_source_discovery_payload(payload):
        resolved_payload = load_source_payload(payload)
        competitor = str(payload.get("competitor", "")).strip().lower()
        if source in {"auto", "claude_code_jsonl"}:
            resolved_source = _MIGRATION_SOURCE_TO_ADAPTER.get(competitor, "auto")
    elif isinstance(payload.get("_discovery_root"), str):
        resolved_payload = payload

    if _is_instruction_only_source_payload(resolved_payload):
        return _instruction_only_source_dry_run(resolved_payload)

    if resolved_source == "claude":
        return dry_run_native_json(resolved_payload)

    detected = _detect_source(resolved_payload) if resolved_source == "auto" else resolved_source
    if detected == "native_json":
        return dry_run_native_json(resolved_payload)
    if detected == "myrm_archive":
        return dry_run_myrm_archive(resolved_payload)
    if detected == "agentmemory":
        return dry_run_agentmemory(resolved_payload)
    if detected == "claude_code_jsonl":
        return dry_run_claude_code_jsonl(resolved_payload)
    if detected == "hermes":
        return dry_run_hermes(resolved_payload)
    if detected == "openclaw":
        return dry_run_openclaw(resolved_payload)
    if detected == "cursor_rules":
        return dry_run_cursor(resolved_payload)
    if detected == "codex":
        return dry_run_codex(resolved_payload)
    if detected == "mem0":
        return dry_run_mem0(resolved_payload)
    return unsupported_result(to_memory_import_source(detected), WARNING_UNSUPPORTED_SOURCE)


def _detect_source(payload: dict[str, object]) -> MemoryImportSource:
    """Auto-detect the import source from payload structure."""

    tagged = _detect_source_from_payload_tag(payload)
    if tagged is not None:
        return tagged

    if is_myrm_archive(payload):
        return "myrm_archive"
    if is_claude_code_jsonl(payload):
        return "claude_code_jsonl"
    if _is_hermes_payload(payload):
        return "hermes"
    if _is_openclaw_payload(payload):
        return "openclaw"
    if _is_cursor_payload(payload):
        return "cursor_rules"
    if _is_codex_payload(payload):
        return "codex"
    if is_mem0_payload(payload):
        return "mem0"
    data = payload.get("data")
    if isinstance(data, dict):
        return "native_json"
    if SUPPORTED_NATIVE_BUCKETS.intersection(payload.keys()):
        return "native_json"
    if {"sessions", "observations", "memories", "summaries"}.issubset(payload.keys()):
        return "agentmemory"
    return "unknown"


_INSTRUCTION_ONLY_SOURCES = frozenset({"claude", "cursor", "codex"})


def _is_instruction_only_source_payload(payload: dict[str, object]) -> bool:
    """True when external source content lives only in the instruction lane (memory payload empty)."""

    competitor = str(payload.get("_source", "")).strip().lower()
    if competitor not in _INSTRUCTION_ONLY_SOURCES:
        return False
    metadata_keys = {"_source", "_discovery_root", "_load_error"}
    return not set(payload.keys()) - metadata_keys


def _instruction_only_source_dry_run(payload: dict[str, object]) -> MemoryImportDryRunResult:
    """Return a ready dry-run when memory lane is intentionally empty after split."""

    from myrm_agent_harness.toolkits.memory import MemoryImportDryRunSummary

    competitor = str(payload.get("_source", "")).strip().lower()
    adapter_source = resolve_migration_source(competitor)
    harness_source = to_memory_import_source(
        adapter_source if adapter_source not in {"auto"} else competitor,
    )
    return MemoryImportDryRunResult(
        summary=MemoryImportDryRunSummary(
            source=harness_source,
            version="1",
            total_items=0,
            mapped_items=0,
            unmapped_items=0,
            status="ready",
        ),
        mappings=[],
        warnings=[],
        normalized_data={},
    )


def _detect_source_from_payload_tag(payload: dict[str, object]) -> MemoryImportSource | None:
    """Prefer explicit ``_source`` from source loader over structural heuristics."""

    raw = payload.get("_source")
    if not isinstance(raw, str):
        return None
    return _SOURCE_TAG_TO_IMPORT.get(raw.strip().lower())


def _is_hermes_payload(payload: dict[str, object]) -> bool:
    """Detect Hermes data: has ``_source`` == 'hermes' or characteristic Markdown file keys."""

    raw_source = payload.get("_source")
    if isinstance(raw_source, str):
        normalized = raw_source.strip().lower()
        if normalized and normalized != "hermes":
            return False
    if payload.get("_source") == "hermes":
        return True
    hermes_keys = {"soul_md", "memory_md", "user_md"}
    return bool(hermes_keys.intersection(payload.keys()))


def _is_openclaw_payload(payload: dict[str, object]) -> bool:
    """Detect OpenClaw data: has ``_source`` == 'openclaw' or characteristic session/memory keys."""

    if payload.get("_source") == "openclaw":
        return True
    return isinstance(payload.get("openclaw_sessions"), list) or isinstance(payload.get("openclaw_memory"), list)


def _is_cursor_payload(payload: dict[str, object]) -> bool:
    """Detect Cursor data: has ``_source`` == 'cursor' or characteristic rules key."""

    if payload.get("_source") == "cursor_rules":
        return True
    return isinstance(payload.get("cursor_rules"), list) or isinstance(payload.get("cursor_settings"), dict)


def _is_codex_payload(payload: dict[str, object]) -> bool:
    """Detect Codex data: has ``_source`` == 'codex' or characteristic codex keys."""

    if payload.get("_source") == "codex":
        return True
    return isinstance(payload.get("codex_instructions"), str) or isinstance(payload.get("codex_settings"), dict)
