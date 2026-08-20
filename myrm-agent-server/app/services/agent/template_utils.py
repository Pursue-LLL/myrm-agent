"""Shared utilities for agent template instantiation.

[INPUT]
- assets/prebuilt_agents/*.yaml (POS: agent template seed files)
- app.core.skills.store::skills_service (POS: skill store singleton for skill enablement)

[OUTPUT]
- PREBUILT_AGENTS_DIR: path to prebuilt agent assets
- resolve_i18n(): multi-language dict → single string
- ensure_skills_enabled(): pre-flight skill check and enablement

[POS]
Service-level shared utilities reused by both API templates router and
onboarding presets. Avoids services-layer importing from api-layer.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_SERVER_ROOT = Path(__file__).resolve().parents[3]
PREBUILT_AGENTS_DIR = str(_SERVER_ROOT / "assets" / "prebuilt_agents")


class SkillEnablementError(Exception):
    """Raised when a required prebuilt skill cannot be enabled."""

    def __init__(self, skill_id: str, template_id: str, detail: str) -> None:
        self.skill_id = skill_id
        self.template_id = template_id
        super().__init__(detail)


def resolve_i18n(value: Any, accept_language: str | None) -> str:
    """Resolve a multi-language dictionary to a single string based on Accept-Language.

    If value is a string, returns it directly.
    """
    if not isinstance(value, dict):
        return str(value) if value is not None else ""

    lang = "en"
    if accept_language:
        if "zh" in accept_language.lower():
            lang = "zh"

    if lang in value:
        return value[lang]

    for k in value:
        if k.startswith(lang):
            return value[k]

    if "en" in value:
        return value["en"]

    return next(iter(value.values()), "")


async def ensure_skills_enabled(prebuilt_skill_ids: list[str], template_id: str) -> None:
    """Pre-flight check and enable all required skills.

    Raises SkillEnablementError if a skill is missing or cannot be enabled.
    """
    from app.core.skills.store.service import skills_service

    for skill_id in prebuilt_skill_ids:
        skill = await skills_service.get_skill(skill_id)
        if not skill:
            raise SkillEnablementError(
                skill_id,
                template_id,
                f"Template requires skill '{skill_id}' which does not exist in the system.",
            )

    for skill_id in prebuilt_skill_ids:
        try:
            await skills_service.user_config.enable_prebuilt_skill(skill_id)
        except Exception as e:
            logger.error(
                "Failed to auto-enable skill %s for template %s: %s",
                skill_id,
                template_id,
                e,
            )
            raise SkillEnablementError(
                skill_id,
                template_id,
                f"Failed to enable required skill '{skill_id}'. Agent creation aborted.",
            ) from e
