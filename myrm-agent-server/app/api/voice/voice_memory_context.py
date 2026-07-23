"""Voice memory ACL context — shared Settings + profile flags for all voice paths.

[INPUT]
- app.core.memory.proactive.settings (POS: enableMemory / sessions opt-in SSOT)
- app.services.agent.profile_resolver (POS: Agent profile resolver)

[OUTPUT]
- VoiceMemoryContext: memory_search_tool ACL flags for voice sessions
- voice_memory_context_from: build flags from already-loaded config slices

[POS]
Voice-layer SSOT for memory read-plane ACL. Keeps Realtime, Gemini Live, and
agent_bridge aligned with Chat memory settings. Callers load profile and settings
once, then call voice_memory_context_from.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from app.core.memory.proactive.settings import (
    resolve_conversation_search_enabled,
    resolve_memory_enabled,
)
from app.services.agent.profile_resolver import resolve_builtin_tool_flags
from app.services.agent.tool_mount import ExecutionSurface, resolve_agent_mount


@dataclass(frozen=True, slots=True)
class VoiceMemoryContext:
    """Runtime ACL for memory_search_tool in voice tool declarations and Agent params."""

    enable_memory: bool
    enable_conversation_search: bool
    enable_wiki: bool

    @property
    def allow_sessions(self) -> bool:
        return self.enable_conversation_search

    @property
    def allow_wiki(self) -> bool:
        return self.enable_wiki and self.enable_memory


def voice_memory_context_from(
    memory_settings: dict[str, object] | None,
    enabled_builtin_tools: Sequence[str],
) -> VoiceMemoryContext:
    """Build voice memory ACL from settings and agent builtin tool flags."""
    tool_flags = resolve_agent_mount(
        ExecutionSurface.VOICE,
        resolve_builtin_tool_flags(enabled_builtin_tools),
    )
    return VoiceMemoryContext(
        enable_memory=resolve_memory_enabled(memory_settings),
        enable_conversation_search=resolve_conversation_search_enabled(memory_settings),
        enable_wiki=bool(tool_flags["enable_wiki"]),
    )
