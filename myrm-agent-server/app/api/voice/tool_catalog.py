"""Voice tool catalog — Realtime tool declarations and shared memory_search_tool builders.

[INPUT]
- app.api.voice.voice_memory_context::VoiceMemoryContext (POS: voice memory ACL SSOT)
- app.api.voice.gemini_live::GeminiFunctionDeclaration (POS: Gemini Live tool schema)

[OUTPUT]
- RealtimeToolDef: OpenAI Realtime function tool schema
- memory_search_corpus_enum: corpus values allowed for the current ACL
- build_memory_search_tool_parameters: JSON schema for memory_search_tool
- build_realtime_memory_tool / build_gemini_memory_tool: provider-specific declarations
- build_realtime_tools: aggregate Realtime session tool list (catalog + always-available + memory ACL)

[POS]
Single place for the Realtime session tool catalog (builtin + always-available tools)
and the ACL-scoped memory_search_tool declarations shared by Realtime and Gemini.
Gemini's own tool catalog stays in gemini_live.py under GeminiFunctionDeclaration schema.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

from app.api.voice.voice_memory_context import VoiceMemoryContext

if TYPE_CHECKING:
    from app.api.voice.gemini_live import GeminiFunctionDeclaration


def memory_search_corpus_enum(ctx: VoiceMemoryContext) -> list[str]:
    """Return corpus enum values exposed to the voice model for the current ACL."""
    if not ctx.enable_memory:
        return ["memory"]
    corpora: list[str] = ["memory"]
    if ctx.allow_wiki:
        corpora.append("wiki")
    if ctx.allow_sessions:
        corpora.append("sessions")
    if len(corpora) > 1:
        corpora.append("all")
    return corpora


def memory_search_tool_description(corpus_enum: list[str]) -> str:
    """Human-readable tool description scoped to allowed corpora."""
    parts = ["Unified search across long-term memory"]
    if "wiki" in corpus_enum:
        parts.append("wiki vault")
    if "sessions" in corpus_enum:
        parts.append("prior conversations")
    scope = ", ".join(parts) + "."
    hints: list[str] = ["Use corpus=memory for preferences and durable facts."]
    if "wiki" in corpus_enum:
        hints.append("Use corpus=wiki for agent wiki docs.")
    if "sessions" in corpus_enum:
        hints.append("Use corpus=sessions for chat history evidence.")
    if "all" in corpus_enum:
        hints.append("Use corpus=all to search every enabled corpus.")
    return f"{scope} {' '.join(hints)}"


def build_memory_search_tool_parameters(corpus_enum: list[str]) -> dict[str, Any]:
    """Build OpenAI/Gemini function parameters for memory_search_tool."""
    properties: dict[str, Any] = {
        "query": {"type": "string", "description": "Search query"},
    }
    if len(corpus_enum) > 1:
        properties["corpus"] = {
            "type": "string",
            "enum": corpus_enum,
            "description": "Corpus to search (default memory)",
        }
    return {
        "type": "object",
        "properties": properties,
        "required": ["query"],
    }


def build_realtime_memory_tool(ctx: VoiceMemoryContext) -> RealtimeToolDef:
    """Build OpenAI Realtime memory_search_tool declaration for the current ACL."""
    corpus_enum = memory_search_corpus_enum(ctx)
    return RealtimeToolDef(
        name="memory_search_tool",
        description=memory_search_tool_description(corpus_enum),
        parameters=build_memory_search_tool_parameters(corpus_enum),
    )


def build_gemini_memory_tool(ctx: VoiceMemoryContext) -> GeminiFunctionDeclaration:
    """Build Gemini Live memory_search_tool declaration for the current ACL."""
    from app.api.voice.gemini_live import GeminiFunctionDeclaration

    corpus_enum = memory_search_corpus_enum(ctx)
    return GeminiFunctionDeclaration(
        name="memory_search_tool",
        description=memory_search_tool_description(corpus_enum),
        parameters=build_memory_search_tool_parameters(corpus_enum),
    )


def include_memory_search_in_voice_catalog(
    ctx: VoiceMemoryContext,
    enabled_builtin_tools: Sequence[str],
) -> bool:
    """Return True when the agent profile and user settings expose memory search."""
    return "memory" in enabled_builtin_tools and ctx.enable_memory


class RealtimeToolDef(BaseModel):
    """OpenAI Realtime function tool declaration schema."""

    type: str = "function"
    name: str
    description: str
    parameters: dict[str, Any]


_REALTIME_TOOL_CATALOG: dict[str, RealtimeToolDef] = {
    "web_search": RealtimeToolDef(
        name="web_search",
        description="Search the web for current information. Use when the user asks about recent events, facts, or anything you're unsure about.",
        parameters={
            "type": "object",
            "properties": {"query": {"type": "string", "description": "Search query"}},
            "required": ["query"],
        },
    ),
    "file_ops": RealtimeToolDef(
        name="file_ops",
        description="Read, write, or list files in the workspace.",
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["read", "write", "list"],
                    "description": "File operation",
                },
                "path": {"type": "string", "description": "File path"},
            },
            "required": ["action", "path"],
        },
    ),
    "code_execute": RealtimeToolDef(
        name="code_execute",
        description="Execute code (Python, shell, etc.) in a sandboxed environment and return the result.",
        parameters={
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "Code to execute"},
                "language": {
                    "type": "string",
                    "description": "Programming language",
                    "default": "python",
                },
            },
            "required": ["code"],
        },
    ),
    "browser": RealtimeToolDef(
        name="browser",
        description="Browse a webpage and extract its content.",
        parameters={
            "type": "object",
            "properties": {"url": {"type": "string", "description": "URL to browse"}},
            "required": ["url"],
        },
    ),
    "kanban": RealtimeToolDef(
        name="kanban",
        description="Manage tasks on the kanban board: create, update, or query tasks.",
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["create", "update", "query"],
                    "description": "Kanban action",
                },
                "description": {
                    "type": "string",
                    "description": "Task description or query",
                },
            },
            "required": ["action", "description"],
        },
    ),
}

_ALWAYS_AVAILABLE_TOOLS: list[RealtimeToolDef] = [
    RealtimeToolDef(
        name="run_background_task",
        description="Delegate a complex task to run in the background. Use for long-running operations that shouldn't block the voice conversation. The result will be available later.",
        parameters={
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": "Detailed description of the task to run",
                }
            },
            "required": ["task"],
        },
    ),
    RealtimeToolDef(
        name="get_background_tasks_status",
        description="Check the status of background tasks. Use when the user asks about task progress or whether a task is done.",
        parameters={
            "type": "object",
            "properties": {},
        },
    ),
    RealtimeToolDef(
        name="cancel_background_task",
        description="Cancel a running background task by its task_id.",
        parameters={
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "ID of the background task to cancel",
                }
            },
            "required": ["task_id"],
        },
    ),
    RealtimeToolDef(
        name="steer_background_task",
        description="Send a new instruction to redirect a running background task.",
        parameters={
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "ID of the background task to steer",
                },
                "instruction": {
                    "type": "string",
                    "description": "New instruction to apply to the task",
                },
            },
            "required": ["task_id", "instruction"],
        },
    ),
]


def build_realtime_tools(
    enabled_builtin_tools: tuple[str, ...] | Sequence[str],
    memory_context: VoiceMemoryContext,
) -> list[RealtimeToolDef]:
    """Build tool definitions for OpenAI Realtime session from agent tools and memory ACL."""
    tools: list[RealtimeToolDef] = list(_ALWAYS_AVAILABLE_TOOLS)
    for tool_key in enabled_builtin_tools:
        if tool_key == "memory":
            if include_memory_search_in_voice_catalog(memory_context, enabled_builtin_tools):
                tools.append(build_realtime_memory_tool(memory_context))
            continue
        if tool_key in _REALTIME_TOOL_CATALOG:
            tools.append(_REALTIME_TOOL_CATALOG[tool_key])
    return tools
