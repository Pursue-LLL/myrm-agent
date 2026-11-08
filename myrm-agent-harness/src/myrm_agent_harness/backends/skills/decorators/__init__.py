"""Skill backend decorators.

Framework-level wrapper that adds cross-cutting behavior to any SkillBackend:
- VersionAwareSkillBackend: activated version snapshot routing
"""

from myrm_agent_harness.backends.skills.decorators.version_aware import (
    VersionAwareSkillBackend,
    session_id_var,
)

__all__ = [
    "VersionAwareSkillBackend",
    "session_id_var",
]
