"""Runtime skill load eligibility (archived / disabled catalog skills).

[INPUT]
- app.core.skills.models::Skill (POS: business skill model)
- myrm_agent_harness.backends.skills.types::SkillLifecycleStatus (POS: curator lifecycle)

[OUTPUT]
- skill_runtime_load_block_reason: why a skill must not enter the agent action space
- filter_skills_for_runtime_load: drop blocked skills for backend construction

[POS]
Single SSOT for production skill load filtering (user backend, get_skills_by_ids).
"""

from __future__ import annotations

import logging

from myrm_agent_harness.backends.skills.types import SkillLifecycleStatus, SkillUsageStats

from app.core.skills.models import Skill
from app.core.storage.types import SkillType

logger = logging.getLogger(__name__)


def _lifecycle_status(skill: Skill) -> SkillLifecycleStatus:
    raw = skill.usage_stats
    if not raw:
        return SkillLifecycleStatus.ACTIVE
    if isinstance(raw, SkillUsageStats):
        return raw.lifecycle_status
    if isinstance(raw, dict):
        try:
            return SkillUsageStats.from_dict(raw).lifecycle_status
        except Exception:
            status = raw.get("lifecycle_status")
            if isinstance(status, str):
                try:
                    return SkillLifecycleStatus(status)
                except ValueError:
                    return SkillLifecycleStatus.ACTIVE
    return SkillLifecycleStatus.ACTIVE


def skill_runtime_load_block_reason(
    skill: Skill,
    *,
    enabled_prebuilt_ids: set[str],
    enabled_local_ids: set[str],
) -> str | None:
    """Return a block reason code, or None when the skill may load at runtime."""
    if skill.type == SkillType.PREBUILT:
        if skill.id not in enabled_prebuilt_ids:
            return "disabled"
    elif skill.type == SkillType.LOCAL:
        if skill.id not in enabled_local_ids:
            return "disabled"

    if _lifecycle_status(skill) == SkillLifecycleStatus.ARCHIVED:
        return "archived"
    return None


def filter_skills_for_runtime_load(
    skills: list[Skill],
    *,
    enabled_prebuilt_ids: set[str],
    enabled_local_ids: set[str],
) -> tuple[list[Skill], list[tuple[str, str]]]:
    """Keep only runtime-loadable skills; return (allowed, [(skill_id, reason), ...])."""
    allowed: list[Skill] = []
    blocked: list[tuple[str, str]] = []
    for skill in skills:
        reason = skill_runtime_load_block_reason(
            skill,
            enabled_prebuilt_ids=enabled_prebuilt_ids,
            enabled_local_ids=enabled_local_ids,
        )
        if reason:
            blocked.append((skill.id, reason))
            logger.info(
                "Skipping skill for runtime load: id=%s name=%s reason=%s",
                skill.id,
                skill.name,
                reason,
            )
            continue
        allowed.append(skill)
    return allowed, blocked
