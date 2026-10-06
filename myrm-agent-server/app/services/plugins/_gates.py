"""Pre-install gates shared by plugin preview and confirm (business layer).

Preview shows exactly what confirm would block, so both read the same predicates:
content size, offline content security scan, and deployment constraints (skills
disabled by the deployment, stdio connectors in cloud).

[INPUT]
- myrm_agent_harness.agent.plugins.models::PluginSkill, PluginMcpServer (POS: parsed plugin models.)
- myrm_agent_harness.agent.skills.evolution.db.store::SkillStore (POS: MAX_SKILL_CONTENT_CHARS size ceiling.)

[OUTPUT]
- scan_skill_security: offline static scan of a skill's content (fail-closed).
- skill_content_too_large: SKILL.md exceeds the storage ceiling.
- skill_block_reason / server_block_reason: machine code why a component cannot be
  installed in this deployment, or ``None``.
- BLOCK_*: block-reason codes (localized by the frontend).

[POS]
Single definition of "can this plugin component be installed here?" for preview and confirm.
"""

from __future__ import annotations

import logging
from typing import Final

from myrm_agent_harness.agent.plugins.models import PluginMcpServer, PluginSkill
from myrm_agent_harness.agent.skills.evolution.db.store import SkillStore

logger = logging.getLogger(__name__)

MAX_SKILL_CONTENT_CHARS: Final = SkillStore.MAX_SKILL_CONTENT_CHARS

BLOCK_SKILLS_DISABLED: Final = "skills_not_supported"
BLOCK_STDIO_DISABLED: Final = "stdio_not_allowed"
BLOCK_OVERSIZED: Final = "oversized_content"
BLOCK_SECURITY: Final = "security_issues"

__all__ = [
    "BLOCK_OVERSIZED",
    "BLOCK_SECURITY",
    "BLOCK_SKILLS_DISABLED",
    "BLOCK_STDIO_DISABLED",
    "MAX_SKILL_CONTENT_CHARS",
    "scan_skill_security",
    "server_block_reason",
    "skill_block_reason",
    "skill_content_too_large",
]


def scan_skill_security(skill: PluginSkill) -> list[str]:
    """Offline static security scan of a skill's content before preview/confirm.

    Returns a list of human-readable issues; an empty list means the skill passed.
    A scanner failure is treated as unsafe (fail-closed) so a broken validator
    never lets a skill install silently or aborts the whole import.
    """
    from myrm_agent_harness.agent.skills.optimization.config import SecurityConfig
    from myrm_agent_harness.agent.skills.optimization.security import SkillSecurityValidator

    try:
        validator = SkillSecurityValidator(config=SecurityConfig())
        full_skill = f"---\nname: {skill.name}\ndescription: {skill.description}\n---\n{skill.content}"
        result = validator.validate_skill(full_skill)
    except Exception as exc:  # fail-closed: unable to verify -> blocked
        logger.warning("Skill security scan failed for %r: %s", skill.name, exc)
        return [f"Security scan failed: {exc}"]
    return result.issues if not result.passed else []


def skill_content_too_large(skill: PluginSkill) -> bool:
    """True when the skill content exceeds the framework's storage limit."""
    return bool(skill.content) and len(skill.content) > MAX_SKILL_CONTENT_CHARS


def skill_block_reason(skill: PluginSkill, *, allows_local_skills: bool) -> str | None:
    """Why ``skill`` cannot be installed here (deployment, size), or ``None``.

    The content security scan is not part of this predicate: it yields
    human-readable issues the caller reports separately.
    """
    if not allows_local_skills:
        return BLOCK_SKILLS_DISABLED
    if skill_content_too_large(skill):
        return BLOCK_OVERSIZED
    return None


def server_block_reason(server: PluginMcpServer, *, allow_stdio: bool) -> str | None:
    """Why ``server`` cannot be installed here (stdio in cloud), or ``None``."""
    if server.server_type == "stdio" and not allow_stdio:
        return BLOCK_STDIO_DISABLED
    return None
