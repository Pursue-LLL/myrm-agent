"""Canonical enabled_builtin_tools IDs — server product-layer SSOT.

Must stay aligned with myrm-agent-frontend ``BUILTIN_TOOL_IDS`` in
``src/store/chat/types/builtinTools.ts``.

[INPUT]
- myrm-agent-frontend ``builtinTools.ts`` (POS: frontend tool ID catalog)

[OUTPUT]
- DEFAULT_ENABLED_BUILTIN_TOOLS: default profile tool list
- BUILTIN_TOOL_IDS / BUILTIN_TOOL_ID_SET: canonical ID catalog
- normalize_enabled_builtin_tools / coerce_enabled_builtin_tools: validation helpers
- strip_legacy_builtin_tool_ids: silent read-path migration for retired tool IDs
- strip_deploy_incompatible_builtin_tools: drop tools unsupported in current deploy mode
- persist_enabled_builtin_tools: DB column write validation

[POS]
Server-side SSOT for enabled_builtin_tools IDs and legacy rejection.
GUI-togglable IDs only; AGENT_BASELINE_BUILTIN_TOOLS (file_ops/code_execute) are stripped at persist and forced at runtime on General track via tool_mount.resolve_agent_mount. Search/Fast (Web `action_mode=fast`) mounts UECD read-only `file_read_tool` via `enable_evicted_read`; write/edit/glob/grep/bash stay off. Channel/IM is General-only.
"""

from __future__ import annotations

from collections.abc import Sequence

DEFAULT_ENABLED_BUILTIN_TOOLS: tuple[str, ...] = (
    "web_search",
    "memory",
    "structured_clarify",
)
"""Default togglable tools when no explicit list is stored (UI-visible switches)."""

AGENT_BASELINE_BUILTIN_TOOLS: tuple[str, ...] = (
    "file_ops",
    "code_execute",
)
"""Agent-mode baseline tools: always Turn1 eager, no frontend toggle (maps to file/bash meta-tools)."""

TOGGLABLE_BUILTIN_TOOL_IDS: tuple[str, ...] = (
    "web_search",
    "memory",
    "wiki",
    "browser",
    "computer_use",
    "image_generation",
    "video_generation",
    "tts",
    "kanban",
    "cron",
    "answer_tool",
    "render_ui",
    "planning",
    "structured_clarify",
    "external_cli",
)
"""IDs shown in BuiltinToolsPanel; excludes AGENT_BASELINE_BUILTIN_TOOLS."""

BUILTIN_TOOL_IDS: tuple[str, ...] = TOGGLABLE_BUILTIN_TOOL_IDS

BUILTIN_TOOL_ID_SET: frozenset[str] = frozenset(
    (*TOGGLABLE_BUILTIN_TOOL_IDS, *AGENT_BASELINE_BUILTIN_TOOLS)
)

LEGACY_REJECTED_BUILTIN_TOOL_IDS: frozenset[str] = frozenset(
    {
        "image_gen",
        "code_interpreter",
        "code_exec",
        "shell_exec",
        "search",
        "bash_tool",
        "task_tracking",
        "canvas",
        "web_crawl",
    }
)

BUILTIN_TOOL_CATALOG: tuple[dict[str, str], ...] = (
    {"id": "web_search", "desc": "Search the web for real-time information"},
    {"id": "memory", "desc": "Recall and save long-term user memory"},
    {"id": "browser", "desc": "Browse web pages and extract structured content"},
    {"id": "computer_use", "desc": "Interact with the desktop for native OS dialogs"},
    {"id": "image_generation", "desc": "Generate images from text descriptions"},
    {"id": "video_generation", "desc": "Generate videos from prompts"},
    {"id": "tts", "desc": "Convert text to speech"},
    {"id": "wiki", "desc": "Query and maintain personal wiki knowledge"},
    {"id": "kanban", "desc": "Manage kanban boards and async tasks"},
    {
        "id": "cron",
        "desc": "Create and manage scheduled tasks from agent chat",
    },
    {"id": "answer_tool", "desc": "Structured final-answer gate for search agents"},
    {"id": "render_ui", "desc": "Render interactive UI artifacts in chat"},
    {"id": "planning", "desc": "Multi-step task progress (main-agent todo_write)"},
    {
        "id": "structured_clarify",
        "desc": "Structured clarification forms when user intent is ambiguous",
    },
    {
        "id": "external_cli",
        "desc": "Delegate tasks to external CLI agents (Claude Code, Codex, Gemini CLI)",
    },
)


class InvalidBuiltinToolIdsError(ValueError):
    """Raised when enabled_builtin_tools contains unknown or legacy IDs."""


def strip_legacy_builtin_tool_ids(tools: Sequence[str]) -> list[str]:
    """Drop legacy IDs when loading persisted profiles (silent read-path migration)."""
    return [
        tool_id
        for raw in tools
        if (tool_id := str(raw).strip())
        and tool_id not in LEGACY_REJECTED_BUILTIN_TOOL_IDS
    ]


def strip_deploy_incompatible_builtin_tools(tools: Sequence[str]) -> list[str]:
    """Drop builtin tools that cannot run in the current deployment mode."""
    result = list(tools)

    if "computer_use" in result:
        from app.config.computer_use_deploy import is_computer_use_deploy_supported

        if not is_computer_use_deploy_supported():
            result = [tool_id for tool_id in result if tool_id != "computer_use"]

    if "external_cli" in result:
        from app.config.external_cli_deploy import is_external_cli_deploy_supported

        if not is_external_cli_deploy_supported():
            result = [tool_id for tool_id in result if tool_id != "external_cli"]

    return result


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
        if tool_id in AGENT_BASELINE_BUILTIN_TOOLS:
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
            parts.append(f"legacy IDs are no longer accepted: {sorted(set(legacy))}")
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


def persist_enabled_builtin_tools(raw: object) -> list[str]:
    """Validate enabled_builtin_tools before writing Agent.enabled_builtin_tools column."""
    if raw is None:
        return list(DEFAULT_ENABLED_BUILTIN_TOOLS)
    if not isinstance(raw, (list, tuple)):
        msg = "enabled_builtin_tools must be a list of tool IDs"
        raise ValueError(msg)
    return normalize_enabled_builtin_tools([str(item) for item in raw])
