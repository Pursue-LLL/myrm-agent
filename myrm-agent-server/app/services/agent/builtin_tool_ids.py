"""Canonical enabled_builtin_tools IDs — server product-layer SSOT.

Must stay aligned with myrm-agent-frontend ``BUILTIN_TOOL_IDS`` in
``src/store/chat/types/builtinTools.ts``.

[INPUT]
- myrm-agent-frontend ``builtinTools.ts`` (POS: frontend tool ID catalog)

[OUTPUT]
- DEFAULT_ENABLED_BUILTIN_TOOLS: default profile tool list
- BUILTIN_TOOL_IDS / BUILTIN_TOOL_ID_SET: canonical ID catalog
- normalize_enabled_builtin_tools / coerce_enabled_builtin_tools: validation helpers

[POS]
Server-side SSOT for enabled_builtin_tools IDs and legacy rejection.
"""

from __future__ import annotations

from collections.abc import Sequence

DEFAULT_ENABLED_BUILTIN_TOOLS: tuple[str, ...] = ("web_search", "memory")
"""Default profile for agents without an explicit tool list."""

BUILTIN_TOOL_IDS: tuple[str, ...] = (
    "web_search",
    "memory",
    "file_ops",
    "code_execute",
    "wiki",
    "browser",
    "computer_use",
    "image_generation",
    "video_generation",
    "tts",
    "kanban",
    "canvas",
    "answer_tool",
    "render_ui",
    "planning",
    "task_tracking",
)

BUILTIN_TOOL_ID_SET: frozenset[str] = frozenset(BUILTIN_TOOL_IDS)

LEGACY_REJECTED_BUILTIN_TOOL_IDS: frozenset[str] = frozenset(
    {
        "image_gen",
        "code_interpreter",
        "code_exec",
        "shell_exec",
        "search",
        "bash_tool",
    }
)

BUILTIN_TOOL_CATALOG: tuple[dict[str, str], ...] = (
    {"id": "web_search", "desc": "Search the web for real-time information"},
    {"id": "memory", "desc": "Recall and save long-term user memory"},
    {"id": "file_ops", "desc": "Read, write, and edit files in the sandbox"},
    {"id": "code_execute", "desc": "Run shell commands and scripts in the sandbox"},
    {"id": "browser", "desc": "Browse web pages and extract structured content"},
    {"id": "computer_use", "desc": "Interact with the desktop for native OS dialogs"},
    {"id": "image_generation", "desc": "Generate images from text descriptions"},
    {"id": "video_generation", "desc": "Generate videos from prompts"},
    {"id": "tts", "desc": "Convert text to speech"},
    {"id": "wiki", "desc": "Query and maintain personal wiki knowledge"},
    {"id": "kanban", "desc": "Manage kanban boards and async tasks"},
    {"id": "canvas", "desc": "Read and update the visual canvas workspace"},
    {"id": "answer_tool", "desc": "Structured final-answer gate for search agents"},
    {"id": "render_ui", "desc": "Render interactive UI artifacts in chat"},
    {"id": "planning", "desc": "Multi-step task planning"},
    {"id": "task_tracking", "desc": "Lightweight execution checklist tracking"},
)


class InvalidBuiltinToolIdsError(ValueError):
    """Raised when enabled_builtin_tools contains unknown or legacy IDs."""


def normalize_enabled_builtin_tools(tools: Sequence[str]) -> list[str]:
    """Validate and deduplicate enabled_builtin_tools preserving order."""
    normalized: list[str] = []
    seen: set[str] = set()
    invalid: list[str] = []
    legacy: list[str] = []

    for raw in tools:
        tool_id = str(raw).strip()
        if not tool_id:
            continue
        if tool_id in LEGACY_REJECTED_BUILTIN_TOOL_IDS:
            legacy.append(tool_id)
            continue
        if tool_id not in BUILTIN_TOOL_ID_SET:
            invalid.append(tool_id)
            continue
        if tool_id in seen:
            continue
        seen.add(tool_id)
        normalized.append(tool_id)

    if legacy or invalid:
        parts: list[str] = []
        if legacy:
            parts.append(
                f"legacy IDs are no longer accepted: {sorted(set(legacy))}"
            )
        if invalid:
            parts.append(
                f"unknown IDs: {sorted(set(invalid))}; "
                f"valid: {sorted(BUILTIN_TOOL_ID_SET)}"
            )
        raise InvalidBuiltinToolIdsError("; ".join(parts))

    return normalized


def coerce_enabled_builtin_tools(
    tools: Sequence[str] | None,
    *,
    default: Sequence[str] = DEFAULT_ENABLED_BUILTIN_TOOLS,
) -> list[str]:
    """Normalize tools or return a copy of *default* when *tools* is None."""
    if tools is None:
        return list(default)
    return normalize_enabled_builtin_tools(tools)
