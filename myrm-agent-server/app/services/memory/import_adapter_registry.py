"""Memory import adapter registry.

[INPUT]
myrm_agent_harness.toolkits.memory::MemoryImportSource (POS: Framework memory reliability kit)

[OUTPUT]
memory_import_supported_sources, memory_import_adapter_status: content-free import adapter readiness registry.

[POS]
Single-user import adapter registry. Provides consistent source readiness
status for dry-run import and the personal brain command center.
"""

from __future__ import annotations

from typing import Literal

from myrm_agent_harness.toolkits.memory import MemoryImportSource

MemoryImportAdapterStatus = Literal["ready", "planned", "missing"]

_SUPPORTED_SOURCES: tuple[str, ...] = (
    "native-json",
    "myrm-archive",
    "agentmemory",
    "gbrain",
    "memweaver",
    "claude-code",
    "hermes",
    "openclaw",
    "cursor",
    "codex",
    "windsurf",
    "trae",
    "mem0",
)
_ADAPTER_STATUS: dict[str, MemoryImportAdapterStatus] = {
    "native-json": "ready",
    "myrm-archive": "ready",
    "agentmemory": "ready",
    "gbrain": "missing",
    "memweaver": "missing",
    "claude-code": "ready",
    "hermes": "ready",
    "openclaw": "ready",
    "cursor": "ready",
    "codex": "ready",
    "windsurf": "ready",
    "trae": "ready",
    "mem0": "ready",
}
_SOURCE_LABELS: dict[MemoryImportSource, str] = {
    "native_json": "native-json",
    "myrm_archive": "myrm-archive",
    "agentmemory": "agentmemory",
    "gbrain": "gbrain",
    "memweaver": "memweaver",
    "claude_code_jsonl": "claude-code",
    "hermes": "hermes",
    "openclaw": "openclaw",
    "cursor_rules": "cursor",
    "codex": "codex",
    "windsurf": "windsurf",
    "trae": "trae",
    "mem0": "mem0",
    "unknown": "unknown",
}


def memory_import_supported_sources() -> list[str]:
    """Return display-order supported import sources."""

    return list(_SUPPORTED_SOURCES)


def memory_import_adapter_status() -> dict[str, MemoryImportAdapterStatus]:
    """Return content-free adapter readiness status."""

    return dict(_ADAPTER_STATUS)


def import_source_label(source: MemoryImportSource | str) -> str:
    """Return the user-visible source label used by migration provenance."""

    for raw_source, label in _SOURCE_LABELS.items():
        if source == raw_source:
            return label
    return str(source).replace("_", "-")
