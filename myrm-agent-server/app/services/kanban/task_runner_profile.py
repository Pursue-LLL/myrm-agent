"""Agent profile resolution for KanbanTaskRunner."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from app.services.agent.profile_resolver import DEFAULT_ENABLED_BUILTIN_TOOLS

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class _ResolvedProfile:
    """Subset of ResolvedAgentProfile needed by KanbanTaskRunner."""

    agent_type: str
    system_prompt: str | None
    model: str | None
    skill_ids: tuple[str, ...]
    subagent_ids: tuple[str, ...] | None
    security_overrides: dict[str, object] | None
    max_iterations: int | None
    memory_policy: object | None
    memory_decay_profile: str | None
    engine_params: dict[str, object] | None
    auto_restore_domains: tuple[str, ...]
    enabled_builtin_tools: tuple[str, ...]

    @classmethod
    def from_resolved(cls, resolved: object) -> _ResolvedProfile:
        return cls(
            agent_type=getattr(resolved, "agent_type", "individual"),
            system_prompt=getattr(resolved, "system_prompt", None),
            model=getattr(resolved, "model", None),
            skill_ids=getattr(resolved, "skill_ids", ()),
            subagent_ids=getattr(resolved, "subagent_ids", None),
            security_overrides=getattr(resolved, "security_overrides", None),
            max_iterations=getattr(resolved, "max_iterations", None),
            memory_policy=getattr(resolved, "memory_policy", None),
            memory_decay_profile=getattr(resolved, "memory_decay_profile", None),
            engine_params=getattr(resolved, "engine_params", None),
            auto_restore_domains=getattr(resolved, "auto_restore_domains", ()),
            enabled_builtin_tools=getattr(
                resolved,
                "enabled_builtin_tools",
                DEFAULT_ENABLED_BUILTIN_TOOLS,
            ),
        )


async def resolve_agent_profile(agent_id: str | None) -> _ResolvedProfile | None:
    if not agent_id:
        return None
    try:
        from app.services.agent.profile_resolver import get_agent_profile_resolver

        resolved = await get_agent_profile_resolver().resolve(agent_id)
        if resolved is None:
            logger.warning("Agent %s not found, using default profile", agent_id)
            return None
        return _ResolvedProfile.from_resolved(resolved)
    except Exception as exc:
        logger.warning("Failed to resolve agent %s: %s", agent_id, exc)
        return None
