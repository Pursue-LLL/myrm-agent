"""Voice tool catalog helpers — dynamic memory_search_tool declarations.

[INPUT]
- app.api.voice.voice_memory_context::VoiceMemoryContext (POS: voice memory ACL SSOT)
- app.api.voice.realtime::RealtimeToolDef (POS: OpenAI Realtime tool schema)
- app.api.voice.gemini_live::GeminiFunctionDeclaration (POS: Gemini Live tool schema)

[OUTPUT]
- memory_search_corpus_enum: corpus values allowed for the current ACL
- build_memory_search_tool_parameters: JSON schema for memory_search_tool
- build_realtime_memory_tool / build_gemini_memory_tool: provider-specific declarations

[POS]
Single place to build memory_search_tool voice declarations that match Chat ACL.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from app.api.voice.voice_memory_context import VoiceMemoryContext

if TYPE_CHECKING:
    from app.api.voice.gemini_live import GeminiFunctionDeclaration
    from app.api.voice.realtime import RealtimeToolDef


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
    from app.api.voice.realtime import RealtimeToolDef

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
