"""Resolve filesystem roots for skills disabled in user config.

[INPUT]
app.core.skills.store.service::SkillsService (POS: 技能目录枚举)
app.core.skills.store.user_config::UserSkillConfigManager (POS: 用户启用/禁用配置)
app.platform_utils::get_storage_provider (POS: 存储后端)

[OUTPUT]
collect_disabled_skill_roots: 返回未启用技能的 storage_path 根目录列表

[POS]
技能禁用根路径解析。供 orchestrator 在启动时排除 disabled skill 文件树，避免 LLM 误读未授权技能。
"""

from __future__ import annotations

import logging

from myrm_agent_harness.toolkits.storage.types import SkillType

from app.core.skills.models import Skill
from app.core.skills.store.service import SkillsService
from app.core.skills.store.user_config import UserSkillConfigManager
from app.platform_utils import get_storage_provider

logger = logging.getLogger(__name__)


async def collect_disabled_skill_roots() -> list[str]:
    """Return storage_path roots for skills not enabled in the user catalog."""
    storage = get_storage_provider()
    config_manager = UserSkillConfigManager(storage)
    user_config = await config_manager.get_config()

    enabled_prebuilt = set(user_config.enabled_prebuilt_ids)
    enabled_local = set(user_config.enabled_local_skill_ids)

    service = SkillsService(storage)
    try:
        all_skills = await service.list_skills(skill_type=None)
    except Exception as exc:
        logger.warning("Failed to list skills for disabled_skill_roots: %s", exc)
        return []

    disabled: list[str] = []
    for skill in all_skills:
        if _is_skill_enabled(skill, enabled_prebuilt, enabled_local):
            continue
        root = skill.storage_path.strip()
        if root:
            disabled.append(root)
    return disabled


def _is_skill_enabled(
    skill: Skill,
    enabled_prebuilt: set[str],
    enabled_local: set[str],
) -> bool:
    if skill.type == SkillType.PREBUILT:
        return skill.id in enabled_prebuilt
    if skill.type == SkillType.LOCAL:
        return skill.id in enabled_local
    return True
