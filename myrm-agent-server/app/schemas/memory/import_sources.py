"""Canonical memory import source vocabulary (single source of truth).

[INPUT]
None (pure definitions).

[OUTPUT]
ImportSource: strict union of every import source the memory import pipeline can
dispatch; ImportRequestSource: the API-level union accepted on requests
(``auto`` plus every concrete source); IMPORT_SOURCE_IDS: runtime view of the
union for contract tests and registry checks.

[POS]
Shared contract leaf of the schemas layer. The API request schema, the import
adapter dispatcher, the migration source manifest and the command-center
projection all derive from this module, so a new source is declared once instead
of drifting across five hand-maintained unions.
"""

from __future__ import annotations

from typing import Literal, get_args

# Order groups the vocabulary for readability only; behavior never depends on it.
ImportSource = Literal[
    # Native / Myrm-owned formats
    "native_json",
    "myrm_archive",
    # Third-party framework exports
    "agentmemory",
    "gbrain",
    "plur",
    "mem0",
    "chatgpt",
    "gemini",
    # Coding-agent sources
    "claude",
    "claude_code_jsonl",
    "cursor_rules",
    "codex",
    "windsurf",
    "trae",
    "hermes",
    "openclaw",
    "pi",
    # Free-text lane (paste import)
    "pasted_memory",
]

ImportRequestSource = Literal["auto"] | ImportSource

IMPORT_SOURCE_IDS: tuple[str, ...] = tuple(get_args(ImportSource))

# Presentation labels persisted with import review sessions and rollback previews.
_IMPORT_SOURCE_LABELS: dict[str, str] = {
    "native_json": "native-json",
    "myrm_archive": "myrm-archive",
    "claude_code_jsonl": "claude-code",
    "cursor_rules": "cursor",
    "pasted_memory": "pasted-memory",
}


def import_source_label(source: str) -> str:
    """Return the user-visible label recorded with import sessions."""

    normalized = str(source).strip()
    if not normalized:
        return "unknown"
    return _IMPORT_SOURCE_LABELS.get(normalized, normalized.replace("_", "-"))
