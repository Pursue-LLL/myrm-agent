"""技能服务

提供技能的增删改查功能。

技能存储结构：
- skills/prebuilt/{skill_name}/ - 预构建技能
- users/{user_id}/config/skills.json - 用户技能配置
"""

from __future__ import annotations

import json
import logging
import mimetypes
from datetime import datetime

from myrm_agent_harness.agent.skills.discovery.sanitizer import (
    SKILL_MD_FILE as SKILL_MD_FILE,
)
from myrm_agent_harness.agent.skills.discovery.sanitizer import (
    SKILL_NAME_PATTERN as SKILL_NAME_PATTERN,
)
from myrm_agent_harness.agent.skills.discovery.sanitizer import (
    sanitize_skill_files,
)
from myrm_agent_harness.toolkits.storage.base import StorageProvider
from myrm_agent_harness.toolkits.storage.factory import get_storage_provider
from myrm_agent_harness.toolkits.storage.paths import (
    SKILL_METADATA_FILE,
    get_skill_file_path,
    get_skill_metadata_path,
    get_skill_storage_path,
)

from ..models import Skill, SkillType
from ..providers.local import LocalSkillsProvider, is_sandbox_mode
from . import reader
from .user_config import UserSkillConfigManager

logger = logging.getLogger(__name__)


class SkillsService:
    """技能服务

    管理技能的增删改查，支持：
    - prebuilt: 预构建技能（对象存储）
    - local: 本地文件系统技能（只读）

    用户配置操作通过 user_config 属性直接访问 UserSkillConfigManager。
    """

    def __init__(self, storage: StorageProvider | None = None):
        self._storage = storage
        self._user_config: UserSkillConfigManager | None = None
        self._local_skills: LocalSkillsProvider | None = None

    @property
    def storage(self) -> StorageProvider:
        if self._storage is None:
            self._storage = get_storage_provider()
        return self._storage

    @property
    def user_config(self) -> UserSkillConfigManager:
        if self._user_config is None:
            self._user_config = UserSkillConfigManager(self.storage)
        return self._user_config

    @property
    def local_skills(self) -> LocalSkillsProvider:
        if self._local_skills is None:
            self._local_skills = LocalSkillsProvider()
        return self._local_skills

    # ========================================================================
    # Create
    # ========================================================================

    async def create_skill(
        self,
        name: str,
        description: str,
        skill_type: SkillType,
        files: dict[str, bytes],
        category: str | None = None,
        tags: list[str] | None = None,
    ) -> Skill:
        """创建预构建技能"""
        files = sanitize_skill_files(files)
        self._validate_skill_input(name, files)
        return await self._create_prebuilt_skill(name, description, files, category, tags)

    def _validate_skill_input(self, name: str, files: dict[str, bytes]) -> None:
        if SKILL_MD_FILE not in files:
            raise ValueError(f"Missing required file: {SKILL_MD_FILE}")
        if not name or not name.strip():
            raise ValueError("Skill name cannot be empty")
        if len(name) > 64:
            raise ValueError("Skill name cannot exceed 64 characters")
        if not SKILL_NAME_PATTERN.match(name):
            raise ValueError("Skill name must start with a letter and contain only letters, numbers, underscores, or hyphens")

    async def _create_prebuilt_skill(
        self,
        name: str,
        description: str,
        files: dict[str, bytes],
        category: str | None,
        tags: list[str] | None,
    ) -> Skill:
        from myrm_agent_harness.utils.text_utils import get_token_count

        skill_id = name
        storage_path = get_skill_storage_path(SkillType.PREBUILT, skill_id)

        # Calculate token cost from SKILL.md
        token_cost = None
        if SKILL_MD_FILE in files:
            try:
                md_content = files[SKILL_MD_FILE].decode("utf-8", errors="replace")
                token_cost = get_token_count(md_content)
            except Exception as e:
                logger.warning(f"Failed to calculate token cost for skill {name}: {e}")

        skill = Skill(
            id=skill_id,
            type=SkillType.PREBUILT,
            name=name,
            description=description,
            storage_path=storage_path,
            category=category,
            tags=tags or [],
            token_cost=token_cost,
        )

        for filename, content in files.items():
            file_path = get_skill_file_path(SkillType.PREBUILT, skill_id, filename)
            content_type, _ = mimetypes.guess_type(filename)
            await self.storage.write(file_path, content, content_type)

        metadata_path = get_skill_metadata_path(SkillType.PREBUILT, skill_id)
        await self.storage.write_text(metadata_path, json.dumps(skill.to_dict(), indent=2))

        logger.warning(f"✅ 创建预构建技能: {skill_id} ({name})")
        return skill

    # ========================================================================
    # Read
    # ========================================================================

    async def get_skill(self, skill_id: str) -> Skill | None:
        """获取技能（按优先级查找：local → prebuilt）"""
        skill = None
        if skill_id.startswith("local::"):
            if not is_sandbox_mode():
                skill = self.local_skills.get_skill_by_id(skill_id)
        else:
            prebuilt_path = get_skill_metadata_path(SkillType.PREBUILT, skill_id)
            try:
                if await self.storage.exists(prebuilt_path):
                    content = await self.storage.read_text(prebuilt_path)
                    skill = Skill.from_dict(json.loads(content))
            except Exception:
                pass

        if skill:
            # Merge runtime is_active status from SQLite
            store = None
            try:
                from app.core.skills.store.evolution_store import get_evolution_skill_store

                store = get_evolution_skill_store()
                db_record = store.get_skill(skill.id)
                if db_record is not None:
                    skill.is_active = db_record.is_active
            except Exception as e:
                logger.error("Failed to merge is_active status from SQLite for %s: %s", skill.id, e)
            finally:
                if store:
                    store.close()

        return skill

    async def list_skills(
        self,
        skill_type: SkillType | None = None,
        sort_by: str = "name",
        order: str = "asc",
        workspace_root: str | None = None,
    ) -> list[Skill]:
        """List skills filtered by type.

        Applies user trust overrides: skills in UserSkillConfig.trusted_skill_ids
        are elevated to trust="trusted".
        """
        skills: list[Skill] = []

        if skill_type is None or skill_type == SkillType.PREBUILT:
            skills.extend(await reader.list_prebuilt_skills(self.storage))

        if skill_type is None or skill_type == SkillType.LOCAL:
            skills.extend(await reader.list_local_skills(self.user_config))

        if skill_type is None or skill_type == SkillType.WORKSPACE:
            skills.extend(reader.list_workspace_skills(workspace_root))

        config = await self.user_config.get_config()
        if config.trusted_skill_ids:
            trusted_set = set(config.trusted_skill_ids)
            for skill in skills:
                if skill.id in trusted_set:
                    skill.user_trusted = True
                    if skill.trust != "trusted":
                        skill.trust = "trusted"

        # Merge runtime is_active status from SQLite
        store = None
        try:
            from app.core.skills.store.evolution_store import get_evolution_skill_store

            store = get_evolution_skill_store()
            for skill in skills:
                # Use skill.id for lookup as it matches storage_skill_id
                db_record = store.get_skill(skill.id)
                if db_record is not None:
                    skill.is_active = db_record.is_active
        except Exception as e:
            logger.error("Failed to merge is_active status from SQLite: %s", e)
        finally:
            if store:
                store.close()

        return reader.sort_skills(skills, sort_by, order)

    async def get_skill_file(self, skill_id: str, filename: str) -> bytes | None:
        """获取技能文件内容"""
        skill = await self.get_skill(skill_id)
        return await reader.get_skill_file(skill, filename, self.storage)

    async def list_skill_files(self, skill_id: str) -> list[str]:
        """列出技能的所有文件"""
        skill = await self.get_skill(skill_id)
        return await reader.list_skill_files(skill, self.storage)

    async def download_skill_to_workspace(
        self,
        skill_id: str,
        target_path: str,
        target_storage: StorageProvider | None = None,
        force: bool = False,
    ) -> bool:
        """下载技能到目标路径（支持版本号增量下载）"""
        skill = await self.get_skill(skill_id)
        if not skill:
            logger.warning(f"⚠️ Skill not found: {skill_id}")
            return False
        return await reader.download_skill_to_workspace(skill, target_path, self.storage, target_storage, force)

    # ========================================================================
    # Update
    # ========================================================================

    async def update_skill(
        self,
        skill_id: str,
        name: str | None = None,
        description: str | None = None,
        category: str | None = None,
        tags: list[str] | None = None,
        is_active: bool | None = None,
        version: str | None = None,
    ) -> Skill | None:
        """更新技能元数据"""
        skill = await self.get_skill(skill_id)
        if not skill:
            return None

        if skill.type == SkillType.LOCAL:
            logger.warning(f"⚠️ Cannot update local skill: {skill_id}")
            return None

        from dataclasses import replace

        updated_skill = replace(
            skill,
            name=name if name is not None else skill.name,
            description=description if description is not None else skill.description,
            category=category if category is not None else skill.category,
            tags=tags if tags is not None else skill.tags,
            is_active=is_active if is_active is not None else skill.is_active,
            version=version if version is not None else skill.version,
            updated_at=datetime.utcnow(),
        )

        metadata_path = f"{updated_skill.storage_path}/{SKILL_METADATA_FILE}"
        await self.storage.write_text(metadata_path, json.dumps(updated_skill.to_dict(), indent=2))

        logger.warning(f"✅ 更新技能: {skill_id} (v{updated_skill.version})")
        return updated_skill

    # ========================================================================
    # Delete
    # ========================================================================

    async def delete_skill(self, skill_id: str) -> bool:
        """删除技能"""
        skill = await self.get_skill(skill_id)
        if not skill:
            return False

        if skill.type == SkillType.LOCAL:
            logger.warning(f"⚠️ Cannot delete local skill: {skill_id}")
            return False
        return await self._delete_prebuilt_skill(skill)

    async def _delete_prebuilt_skill(self, skill: Skill) -> bool:
        logger.warning(f"🗑️ 删除预构建技能: {skill.id}")
        try:
            files = await self.storage.list(skill.storage_path)
            for file_path in files:
                try:
                    await self.storage.delete(file_path)
                except Exception as e:
                    logger.warning(f"Failed to delete file {file_path}: {e}")
        except Exception as e:
            logger.warning(f"Failed to list files for deletion: {e}")
        return True

    # ========================================================================
    # 复合查询
    # ========================================================================

    async def get_user_available_skills(self) -> list[Skill]:
        """获取工作区可用的技能列表（启用的预构建 + 启用的本地技能）"""
        config = await self.user_config.get_config()
        all_prebuilt = await self.list_skills(skill_type=SkillType.PREBUILT)
        enabled_prebuilt = [s for s in all_prebuilt if s.id in config.enabled_prebuilt_ids]
        all_local_skills = await reader.list_local_skills(self.user_config)
        enabled_local_skills = [s for s in all_local_skills if s.id in config.enabled_local_skill_ids]
        return enabled_prebuilt + enabled_local_skills

    async def get_skills_by_ids(self, skill_ids: list[str]) -> list[Skill]:
        """根据技能 ID 列表获取技能"""
        if not skill_ids:
            return []

        all_prebuilt = await self.list_skills(skill_type=SkillType.PREBUILT)
        local_skills: list[Skill] = await reader.list_local_skills(self.user_config)
        all_skills = all_prebuilt + local_skills

        skill_map = {s.id: s for s in all_skills}
        return [skill_map[sid] for sid in skill_ids if sid in skill_map]


__all__ = [
    "SKILL_MD_FILE",
    "SKILL_NAME_PATTERN",
    "SkillsService",
    "skills_service",
]

skills_service = SkillsService()
