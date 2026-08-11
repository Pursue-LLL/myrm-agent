"""Packaging - 技能打包/解包

Server 层 Facade：技能的 ZIP 打包、验证、解包注册与导出脱敏，底层由 myrm_agent_harness 实现。
"""

import logging
from dataclasses import dataclass
from pathlib import Path

from myrm_agent_harness.agent.skills.evolution.core.types import (
    EnvironmentFingerprint,
    EvolutionType,
    SkillLineage,
    SkillRecord,
)
from myrm_agent_harness.agent.skills.market.sanitizer import SKILL_MD_FILE
from myrm_agent_harness.agent.skills.packaging import (
    EVALS_FILE,
    SkillPackageInfo,
    SkillPacker,
    SkillUnpacker,
    is_evals_file,
    is_forbidden_file,
    parse_evals_json,
    parse_skill_md,
    serialize_eval_cases,
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
from myrm_agent_harness.toolkits.storage.paths import SKILL_METADATA_FILE, get_skill_file_path

from ..store.service import SkillsService, skills_service

logger = logging.getLogger(__name__)


def _load_evolution_record(skill_name: str) -> SkillRecord | None:
    """Best-effort load of the active evolution record for a skill name."""
    try:
        from app.core.skills.store.evolution_store import get_evolution_skill_store

        store = get_evolution_skill_store()
        try:
            return store.get_skill_by_name_version(skill_name)
        finally:
            store.close()
    except Exception as exc:
        logger.debug("Evolution record lookup failed for %s: %s", skill_name, exc)
        return None


def _sync_skill_md_version(content: str, version: str) -> str:
    """Sync SKILL.md frontmatter version so exported package reflects real lineage version."""
    lines = content.split("\n")
    if not lines or lines[0].strip() != "---":
        return content
    fm_end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            fm_end = i
            break
    if fm_end is None:
        return content
    for i in range(1, fm_end):
        stripped = lines[i].strip()
        if stripped.startswith("version:"):
            indent = lines[i][: len(lines[i]) - len(lines[i].lstrip())]
            lines[i] = f"{indent}version: {version}"
            return "\n".join(lines)
    lines.insert(fm_end, f"version: {version}")
    return "\n".join(lines)


@dataclass
class PackageResult:
    """打包结果"""

    success: bool
    zip_content: bytes | None
    filename: str | None
    error: str | None = None
    redactions: dict[str, list[Redaction]] | None = None  # filename -> list of redactions
    is_safe: bool = True  # True if no redactions were needed or if they were applied and user confirmed
    eval_cases_count: int = 0  # 包内 evals.json 回归门禁用例数


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

    async def package_skill(
        self,
        skill_id: str,
        preview_only: bool = False,
        apply_redactions: bool = False,
        ignored_redactions: dict[str, list[int]] | None = None,
    ) -> PackageResult:
        """从 Server 的 SkillsService 获取并打包已注册的技能

        Args:
            skill_id: 技能 ID
            preview_only: 如果为 True，仅返回脱敏预览结果，不实际生成 ZIP
            apply_redactions: 如果为 True，将脱敏后的内容写入 ZIP；否则写入原始内容（用户确认无误或忽略警告）
            ignored_redactions: 字典，key 为文件名，value 为该文件中需要忽略脱敏的匹配项索引列表
        """
        ignored_redactions = ignored_redactions or {}
        try:
            skill = await self._skills_svc.get_skill(skill_id)
            if not skill:
                return PackageResult(success=False, zip_content=None, filename=None, error=f"技能不存在: {skill_id}")

            files = await self._skills_svc.list_skill_files(skill_id)
            if not files:
                return PackageResult(success=False, zip_content=None, filename=None, error="技能没有文件")

            # 从 evolution 存储读取回归门禁快照与真实演化版本
            eval_cases_count = 0
            lineage_version: int | None = None
            record = _load_evolution_record(skill.name)
            if record is not None:
                eval_cases_count = len(record.eval_cases or [])
                if record.lineage is not None:
                    lineage_version = record.lineage.version

            file_contents = {}
            all_redactions = {}
            is_safe = True

            for file_path in files:
                if file_path == SKILL_METADATA_FILE:
                    continue
                content = await self._skills_svc.get_skill_file(skill_id, file_path)
                if content:
                    # 导出前同步 frontmatter version，让包内版本与 DB lineage 一致
                    if file_path == SKILL_MD_FILE and lineage_version is not None:
                        text = content.decode("utf-8", errors="replace")
                        synced = _sync_skill_md_version(text, str(lineage_version))
                        if synced != text:
                            content = synced.encode("utf-8")

                    # Perform sanitization check
                    file_ignored_indices = ignored_redactions.get(file_path, [])
                    sanitization_result = content_sanitizer.sanitize(content, file_path, ignored_indices=file_ignored_indices)

                    # If there are redactions (even if we ignore some, if there are remaining ones, it's not safe)
                    # Actually, if we ignored ALL of them, is it safe?
                    # The preview returns all found redactions.
                    # If we are applying redactions, we pass ignored_indices.
                    # The result redactions will only contain the ones that were NOT ignored.
                    if not sanitization_result.is_safe:
                        is_safe = False
                        all_redactions[file_path] = sanitization_result.redactions

                    # Decide which content to pack
                    if apply_redactions and not sanitization_result.is_safe:
                        file_contents[file_path] = sanitization_result.sanitized_content
                    else:
                        file_contents[file_path] = content

            # 追加 evals.json 回归门禁快照（自动脱敏，不进入用户确认流程）
            if record is not None and record.eval_cases:
                evals_text = serialize_eval_cases(skill.name, record.eval_cases)
                evals_sanitized = content_sanitizer.sanitize(evals_text, EVALS_FILE)
                if not evals_sanitized.is_safe:
                    logger.warning(
                        "Skill %s: %d sensitive items auto-redacted inside %s",
                        skill.name,
                        len(evals_sanitized.redactions),
                        EVALS_FILE,
                    )
                file_contents[EVALS_FILE] = evals_sanitized.sanitized_content

            if preview_only:
                return PackageResult(
                    success=True,
                    zip_content=None,
                    filename=None,
                    redactions=all_redactions if all_redactions else None,
                    is_safe=is_safe,
                    eval_cases_count=eval_cases_count,
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
                is_safe=is_safe,
                eval_cases_count=eval_cases_count,
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

        # 剥离包内保留文件 evals.json，避免写入技能存储目录
        files = dict(result.files)
        eval_cases: list[dict[str, object]] | None = None
        for key in list(files.keys()):
            if is_evals_file(key):
                raw = files.pop(key)
                eval_cases = parse_evals_json(raw)
                if eval_cases is None:
                    logger.warning("Skill %s: ignoring invalid %s", info.name, key)
                break

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
                files=files,
            )
            restored_eval_cases = 0
            if eval_cases:
                restored_eval_cases = await self._restore_eval_cases(skill, files, eval_cases)
            logger.warning(f"📦 Skill registered: {skill.id} ({info.name})")
            return UnpackResult(
                success=True,
                skill_id=skill.id,
                skill_name=skill.name,
                restored_eval_cases=restored_eval_cases,
            )
        except Exception as e:
            logger.error(f"Skill unpack failed: {e}")
            return UnpackResult(success=False, error=str(e))

    async def _restore_eval_cases(
        self,
        skill: object,
        files: dict[str, bytes],
        eval_cases: list[dict[str, object]],
    ) -> int:
        """Best-effort restore of package eval_cases into the evolution SkillStore.

        Returns:
            Number of restored eval cases (0 if the skill has no registered record or on failure).
        """
        from ..models import Skill, SkillType

        if not isinstance(skill, Skill):
            return 0
        try:
            from app.core.skills.store.evolution_store import get_evolution_skill_store

            store = get_evolution_skill_store()
            try:
                record = store.get_skill_by_name_version(skill.name)
                if record is None:
                    skill_md = files.get(SKILL_MD_FILE, b"").decode("utf-8", errors="replace")
                    path = get_skill_file_path(SkillType.PREBUILT, skill.id, SKILL_MD_FILE)
                    record = SkillRecord(
                        skill_id=skill.id,
                        name=skill.name,
                        description=skill.description,
                        content=skill_md,
                        path=path,
                        lineage=SkillLineage(
                            evolution_type=EvolutionType.CAPTURED,
                            version=1,
                            created_by="package_import",
                        ),
                        is_active=True,
                        environment=EnvironmentFingerprint(),
                    )
                record.eval_cases = eval_cases
                await store.save_skill(record)
                return len(eval_cases)
            finally:
                store.close()
        except Exception as exc:
            logger.warning("Failed to restore eval_cases for '%s': %s", skill.name, exc)
            return 0


@dataclass
class UnpackResult:
    """解包结果 (Server 业务层包装)"""

    success: bool
    skill_id: str | None = None
    skill_name: str | None = None
    error: str | None = None
    restored_eval_cases: int = 0  # 从包内 evals.json 还原的回归门禁用例数


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
