"""用户技能配置管理

管理用户的技能配置，包括：
- 启用的预构建技能列表
- 本地技能路径和启用状态
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

from myrm_agent_harness.toolkits.storage.base import StorageProvider
from myrm_agent_harness.toolkits.storage.paths import get_user_skill_config_path

from ..models import UserSkillConfig

logger = logging.getLogger(__name__)


class UserSkillConfigManager:
    """用户技能配置管理器

    管理用户的预构建技能启用状态和本地技能配置。
    """

    def __init__(self, storage: StorageProvider):
        self._storage = storage

    @property
    def storage(self) -> StorageProvider:
        return self._storage

    async def _config_file_exists(self) -> bool:
        config_path = get_user_skill_config_path()
        try:
            await self._storage.read_text(config_path)
            return True
        except FileNotFoundError:
            return False

    async def get_config(self) -> UserSkillConfig:
        """获取技能配置"""
        config_path = get_user_skill_config_path()
        try:
            content = await self._storage.read_text(config_path)
            return UserSkillConfig.from_dict(json.loads(content))
        except FileNotFoundError:
            return UserSkillConfig(user_id="sandbox")

    async def ensure_prebuilt_enabled_after_sync(self, prebuilt_skill_ids: list[str]) -> UserSkillConfig:
        """Enable prebuilt skills after seed sync.

        - New install (no config file): enable all seeded prebuilt skills.
        - Existing install: append newly seeded skills unless user disabled them.
        - Always prune enabled/disabled IDs that no longer exist in seeds.
        """
        if not prebuilt_skill_ids:
            return await self.get_config()

        valid_ids = set(prebuilt_skill_ids)
        config_exists = await self._config_file_exists()
        config = await self.get_config()
        changed = False

        pruned_enabled = sorted(sid for sid in config.enabled_prebuilt_ids if sid in valid_ids)
        pruned_disabled = sorted(sid for sid in config.disabled_prebuilt_ids if sid in valid_ids)
        if pruned_enabled != config.enabled_prebuilt_ids:
            config.enabled_prebuilt_ids = pruned_enabled
            changed = True
        if pruned_disabled != config.disabled_prebuilt_ids:
            config.disabled_prebuilt_ids = pruned_disabled
            changed = True

        if not config_exists:
            config.enabled_prebuilt_ids = sorted(prebuilt_skill_ids)
            changed = True
        else:
            enabled = set(config.enabled_prebuilt_ids)
            disabled = set(config.disabled_prebuilt_ids)
            for skill_id in prebuilt_skill_ids:
                if skill_id in disabled or skill_id in enabled:
                    continue
                enabled.add(skill_id)
                changed = True
            if changed:
                config.enabled_prebuilt_ids = sorted(enabled)

        if changed:
            config.updated_at = datetime.now(UTC)
            await self.save_config(config)
            logger.info(
                "Updated prebuilt skill enablement: %d enabled, %d disabled",
                len(config.enabled_prebuilt_ids),
                len(config.disabled_prebuilt_ids),
            )

        return config

    async def save_config(self, config: UserSkillConfig) -> None:
        """保存技能配置"""
        config_path = get_user_skill_config_path()
        await self._storage.write_text(config_path, json.dumps(config.to_dict(), indent=2))

    async def update_config(
        self,
        enabled_prebuilt_ids: list[str] | None = None,
        enabled_local_skill_ids: list[str] | None = None,
        evolution_strategy: str | None = None,
        **_kwargs: object,
    ) -> UserSkillConfig:
        """Update user skill configuration."""
        config = await self.get_config()

        if enabled_prebuilt_ids is not None:
            config.enabled_prebuilt_ids = enabled_prebuilt_ids
        if enabled_local_skill_ids is not None:
            config.enabled_local_skill_ids = enabled_local_skill_ids
        if evolution_strategy is not None:
            config.evolution_strategy = evolution_strategy

        config.updated_at = datetime.now(UTC)
        await self.save_config(config)

        logger.info("Updated user skill config")
        return config

    async def update_local_skill_paths(
        self,
        paths: list[str],
    ) -> UserSkillConfig:
        """更新的本地技能路径配置"""
        config = await self.get_config()
        config.local_skill_paths = paths
        config.updated_at = datetime.now(UTC)
        await self.save_config(config)
        logger.warning(f"✅ 更新本地技能路径: paths={paths}")
        return config

    async def enable_local_skill(self, skill_id: str) -> UserSkillConfig:
        """启用本地技能"""
        config = await self.get_config()
        if skill_id not in config.enabled_local_skill_ids:
            config.enabled_local_skill_ids.append(skill_id)
            config.updated_at = datetime.now(UTC)
            await self.save_config(config)
            logger.warning(f"✅ 启用本地技能: {skill_id}")
        return config

    async def disable_prebuilt_skill(self, skill_id: str) -> UserSkillConfig:
        """Disable a prebuilt skill and record it so seed sync does not re-enable it."""
        config = await self.get_config()
        if skill_id in config.enabled_prebuilt_ids:
            config.enabled_prebuilt_ids.remove(skill_id)
        if skill_id not in config.disabled_prebuilt_ids:
            config.disabled_prebuilt_ids.append(skill_id)
        config.updated_at = datetime.now(UTC)
        await self.save_config(config)
        logger.warning("Disabled prebuilt skill: %s", skill_id)
        return config

    async def enable_prebuilt_skill(self, skill_id: str) -> UserSkillConfig:
        """Enable a prebuilt skill and clear any prior user disable flag."""
        config = await self.get_config()
        if skill_id in config.disabled_prebuilt_ids:
            config.disabled_prebuilt_ids.remove(skill_id)
        if skill_id not in config.enabled_prebuilt_ids:
            config.enabled_prebuilt_ids.append(skill_id)
        config.updated_at = datetime.now(UTC)
        await self.save_config(config)
        logger.warning("Enabled prebuilt skill: %s", skill_id)
        return config

    async def disable_local_skill(self, skill_id: str) -> UserSkillConfig:
        """禁用本地技能"""
        config = await self.get_config()
        if skill_id in config.enabled_local_skill_ids:
            config.enabled_local_skill_ids.remove(skill_id)
            config.updated_at = datetime.now(UTC)
            await self.save_config(config)
            logger.warning(f"🚫 禁用本地技能: {skill_id}")
        return config

    async def update_enabled_local_skills(
        self,
        enabled_ids: list[str],
    ) -> UserSkillConfig:
        """批量更新启用的本地技能列表"""
        config = await self.get_config()
        config.enabled_local_skill_ids = enabled_ids
        config.updated_at = datetime.now(UTC)
        await self.save_config(config)
        logger.warning(f"✅ 更新启用的本地技能: count={len(enabled_ids)}")
        return config

    async def trust_skill(self, skill_id: str) -> UserSkillConfig:
        """Elevate a skill to TRUSTED after security review."""
        config = await self.get_config()
        if skill_id not in config.trusted_skill_ids:
            config.trusted_skill_ids.append(skill_id)
            config.updated_at = datetime.now(UTC)
            await self.save_config(config)
            logger.info("Trusted skill %s", skill_id)
        return config

    async def untrust_skill(self, skill_id: str) -> UserSkillConfig:
        """Revoke trust from a skill, reverting to INSTALLED."""
        config = await self.get_config()
        if skill_id in config.trusted_skill_ids:
            config.trusted_skill_ids.remove(skill_id)
            config.updated_at = datetime.now(UTC)
            await self.save_config(config)
            logger.info("Revoked trust for skill %s", skill_id)
        return config
