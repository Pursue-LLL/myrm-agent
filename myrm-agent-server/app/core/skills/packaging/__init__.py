"""Packaging - 技能打包/解包

提供技能的 ZIP 打包、验证和解包注册功能。
此模块为业务层包装器，底层实现已迁移至 myrm_agent_harness 框架层。
"""

import logging
from dataclasses import dataclass
from pathlib import Path

from myrm_agent_harness.agent.skills.packaging import (
    PackageResult,
    SkillPackageInfo,
    SkillPacker,
    SkillUnpacker,
    is_forbidden_file,
    parse_skill_md,
    validate_skill_zip,
)
from myrm_agent_harness.agent.skills.packaging.validator import (
    ALLOWED_EXTENSIONS,
    FORBIDDEN_PATTERNS,
    MAX_SKILL_ZIP_SIZE,
    suggest_valid_skill_name,
)
from myrm_agent_harness.agent.skills.security.content_sanitizer import Redaction, content_sanitizer
from myrm_agent_harness.toolkits.storage.base import StorageProvider
from myrm_agent_harness.toolkits.storage.paths import SKILL_METADATA_FILE

from ..store.service import SkillsService, skills_service

logger = logging.getLogger(__name__)


@dataclass
class PackageResult:
    """打包结果"""

    success: bool
    zip_content: bytes | None
    filename: str | None
    error: str | None = None
    redactions: dict[str, list[Redaction]] | None = None  # filename -> list of redactions
    is_safe: bool = True  # True if no redactions were needed or if they were applied and user confirmed


class SkillPackagingService:
    """技能打包服务 - 统一入口"""

    def __init__(
        self,
        storage: StorageProvider | None = None,
        skills_svc: SkillsService | None = None,
    ):
        self._packer = SkillPacker()
        self._unpacker = SkillUnpacker()
        self._skills_svc = skills_svc or skills_service

    async def package_skill(self, skill_id: str, preview_only: bool = False, apply_redactions: bool = False) -> PackageResult:
        """从 Server 的 SkillsService 获取并打包已注册的技能
        
        Args:
            skill_id: 技能 ID
            preview_only: 如果为 True，仅返回脱敏预览结果，不实际生成 ZIP
            apply_redactions: 如果为 True，将脱敏后的内容写入 ZIP；否则写入原始内容（用户确认无误或忽略警告）
        """
        try:
            skill = await self._skills_svc.get_skill(skill_id)
            if not skill:
                return PackageResult(success=False, zip_content=None, filename=None, error=f"技能不存在: {skill_id}")

            files = await self._skills_svc.list_skill_files(skill_id)
            if not files:
                return PackageResult(success=False, zip_content=None, filename=None, error="技能没有文件")

            file_contents = {}
            all_redactions = {}
            is_safe = True

            for file_path in files:
                if file_path == SKILL_METADATA_FILE:
                    continue
                content = await self._skills_svc.get_skill_file(skill_id, file_path)
                if content:
                    # Perform sanitization check
                    sanitization_result = content_sanitizer.sanitize(content, file_path)
                    
                    if not sanitization_result.is_safe:
                        is_safe = False
                        all_redactions[file_path] = sanitization_result.redactions
                    
                    # Decide which content to pack
                    if apply_redactions and not sanitization_result.is_safe:
                        file_contents[file_path] = sanitization_result.sanitized_content
                    else:
                        file_contents[file_path] = content

            if preview_only:
                return PackageResult(
                    success=True,
                    zip_content=None,
                    filename=None,
                    redactions=all_redactions if all_redactions else None,
                    is_safe=is_safe
                )

            # Actual packaging
            pack_result = self._packer.package_files(skill.name, skill.version or "1.0.0", file_contents)
            
            # Wrap the harness result to include redaction info
            return PackageResult(
                success=pack_result.success,
                zip_content=pack_result.zip_content,
                filename=pack_result.filename,
                error=pack_result.error,
                redactions=all_redactions if all_redactions else None,
                is_safe=is_safe
            )

        except Exception as e:
            logger.error(f"打包技能失败: {skill_id}, 错误: {e}")
            return PackageResult(success=False, zip_content=None, filename=None, error=str(e))

    async def package_workspace_directory(
        self,
        chat_id: str,
        directory: str = "",
        container_id: str | None = None,
    ) -> PackageResult:
        """将工作空间目录打包为 ZIP"""
        from myrm_agent_harness.toolkits.code_execution import create_workspace_service

        from app.config.settings import settings

        workspace_svc = create_workspace_service(root_dir=Path(settings.database.harness_dir))
        session_id = f"chat_{chat_id}"
        workspace = await workspace_svc.find_by_session_id(session_id)

        if not workspace:
            return PackageResult(success=False, zip_content=None, filename=None, error=f"未找到会话 {chat_id} 的工作空间")

        sandbox_path = Path(workspace_svc.get_workspace_absolute_path(workspace))
        search_dir = sandbox_path / (directory or ".")

        return self._packer.package_directory(search_dir)

    async def validate_skill_zip(self, zip_content: bytes) -> SkillPackageInfo:
        """验证技能 ZIP 包"""
        return validate_skill_zip(zip_content)

    async def unpack_and_register(
        self,
        zip_content: bytes,
        force: bool = False,
    ) -> "UnpackResult":
        """解包并注册技能"""
        result = self._unpacker.unpack(zip_content)
        if not result.success or not result.skill_info or not result.files:
            return UnpackResult(success=False, error=result.error)

        from ..models import SkillType

        info = result.skill_info

        if not force:
            existing_skills = await self._skills_svc.list_skills()
            for skill in existing_skills:
                if skill.name == info.name:
                    return UnpackResult(success=False, error=f"Skill already exists: {info.name}, use force=true to overwrite")

        try:
            skill = await self._skills_svc.create_skill(
                name=info.name,
                description=info.description,
                skill_type=SkillType.PREBUILT,
                files=result.files,
            )
            logger.warning(f"📦 Skill registered: {skill.id} ({info.name})")
            return UnpackResult(success=True, skill_id=skill.id, skill_name=skill.name)
        except Exception as e:
            logger.error(f"Skill unpack failed: {e}")
            return UnpackResult(success=False, error=str(e))

@dataclass
class UnpackResult:
    """解包结果 (Server 业务层包装)"""

    success: bool
    skill_id: str | None = None
    skill_name: str | None = None
    error: str | None = None

skill_packaging_service = SkillPackagingService()

__all__ = [
    "SkillPackagingService",
    "skill_packaging_service",
    "SkillPacker",
    "PackageResult",
    "SkillUnpacker",
    "UnpackResult",
    "SkillPackageInfo",
    "validate_skill_zip",
    "parse_skill_md",
    "suggest_valid_skill_name",
    "is_forbidden_file",
    "MAX_SKILL_ZIP_SIZE",
    "ALLOWED_EXTENSIONS",
    "FORBIDDEN_PATTERNS",
]
