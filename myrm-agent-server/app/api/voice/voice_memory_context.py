"""Voice memory ACL context — shared Settings + profile flags for all voice paths.

[INPUT]
- app.core.channel_bridge.config_loader::load_user_configs (POS: user config loader)
- app.core.memory.proactive.settings (POS: enableMemory / sessions opt-in SSOT)
- app.services.agent.profile_resolver (POS: Agent profile resolver)

[OUTPUT]
- VoiceMemoryContext: memory_search_tool ACL flags for voice sessions
- resolve_voice_memory_context: load flags for an agent_id
- voice_memory_context_from: build flags from already-loaded config slices

[POS]
Voice-layer SSOT for memory read-plane ACL. Keeps Realtime, Gemini Live, and
agent_bridge aligned with Chat memory settings without duplicating resolver logic.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from app.core.memory.proactive.settings import (
    resolve_conversation_search_enabled,
    resolve_memory_enabled,
)
from app.services.agent.profile_resolver import (
    DEFAULT_ENABLED_BUILTIN_TOOLS,
    apply_agent_baseline_tool_flags,
    resolve_builtin_tool_flags,
)


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
    tool_flags = apply_agent_baseline_tool_flags(resolve_builtin_tool_flags(enabled_builtin_tools))
    return VoiceMemoryContext(
        enable_memory=resolve_memory_enabled(memory_settings),
        enable_conversation_search=resolve_conversation_search_enabled(memory_settings),
        enable_wiki=bool(tool_flags["enable_wiki"]),
    )


async def resolve_voice_memory_context(agent_id: str) -> VoiceMemoryContext:
    """Load user settings and agent profile to resolve voice memory ACL."""
    from app.core.channel_bridge.config_loader import load_user_configs
    from app.services.agent.profile_resolver import get_agent_profile_resolver

    configs = await load_user_configs()
    resolver = get_agent_profile_resolver()
    resolved_id = agent_id or "builtin-general"
    profile = await resolver.resolve(resolved_id)
    enabled_builtin_tools = (
        list(profile.enabled_builtin_tools) if profile else list(DEFAULT_ENABLED_BUILTIN_TOOLS)
    )
    return voice_memory_context_from(configs.personal_settings_dict or {}, enabled_builtin_tools)
