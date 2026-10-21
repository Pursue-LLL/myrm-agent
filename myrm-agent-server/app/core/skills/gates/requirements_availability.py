"""Requirement-based skill availability: bins, env and config declared in SKILL.md ``requires``.

[INPUT]
- myrm_agent_harness.backends.skills::evaluate_requires (POS: dependency verdict, process env plus caller env)
- app.core.skills.store.user_config::UserSkillConfigManager, lookup_skill_env (POS: keys saved in skill settings)
- myrm_agent_harness.toolkits.storage.factory::get_storage_provider (POS: process-wide storage provider)

[OUTPUT]
- apply_requirements_availability_to_metadata: re-evaluates Agent runtime SkillMetadata entries
- apply_requirements_availability_to_catalog: re-evaluates Skills page Catalog entries

[POS]
Server business-layer step shared by Catalog and Agent runtime. The harness judges `requires` against the
process environment only; env keys users save in the skills settings live in the server's user config, so
availability is recomputed here with both sources. Skills that declare no requirements are left untouched.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

from myrm_agent_harness.backends.skills import evaluate_requires
from myrm_agent_harness.backends.skills.types import SkillMetadata, SkillRequires
from myrm_agent_harness.toolkits.storage.factory import get_storage_provider

from app.core.skills.models import Skill
from app.core.skills.store.user_config import UserSkillConfigManager, lookup_skill_env

logger = logging.getLogger(__name__)


def _declares_requirements(requires: SkillRequires | None) -> bool:
    return requires is not None and bool(requires.bins or requires.env or requires.config)


async def _load_skill_env_vars() -> dict[str, dict[str, str]]:
    try:
        config = await UserSkillConfigManager(get_storage_provider()).get_config()
    except Exception as exc:
        logger.warning("Skill env unavailable for availability check, using process environment only: %s", exc)
        return {}
    return config.skill_env_vars


async def apply_requirements_availability_to_metadata(skills: Sequence[SkillMetadata]) -> None:
    """Recompute availability of runtime skills that declare ``requires``."""
    declaring = [meta for meta in skills if _declares_requirements(meta.requires)]
    if not declaring:
        return
    skill_env_vars = await _load_skill_env_vars()
    for meta in declaring:
        extra_env = lookup_skill_env(skill_env_vars, meta.name, meta.storage_skill_id)
        meta.available, meta.unavailable_reason = evaluate_requires(meta.requires, extra_env)


async def apply_requirements_availability_to_catalog(skills: Sequence[Skill]) -> None:
    """Recompute availability of Skills page entries that declare ``requires``."""
    declaring = [skill for skill in skills if _declares_requirements(skill.requires)]
    if not declaring:
        return
    skill_env_vars = await _load_skill_env_vars()
    for skill in declaring:
        extra_env = lookup_skill_env(skill_env_vars, skill.name, skill.id)
        skill.available, skill.unavailable_reason = evaluate_requires(skill.requires, extra_env)
