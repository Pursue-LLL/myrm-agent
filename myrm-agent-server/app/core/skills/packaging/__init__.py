"""Packaging - 技能打包/解包

Server 层 Facade：技能的 ZIP 打包、验证、解包注册与导出脱敏，底层由 myrm_agent_harness 实现。
"""

import asyncio
import logging
from datetime import datetime
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
from myrm_agent_harness.agent.skills.security.content_sanitizer import content_sanitizer
from myrm_agent_harness.toolkits.storage.base import StorageProvider
from myrm_agent_harness.toolkits.storage.paths import get_skill_file_path

from ..store.service import SkillsService, skills_service
from ._helpers import _load_evolution_record
from ._models import SKILL_CHANGED_SINCE_PREVIEW, PackageResult, UnpackResult
from .collect import collect_skill_files
from .redaction import redact_files
from .redaction import review_digest as compute_review_digest

logger = logging.getLogger(__name__)


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
        export_format: str = "agent_plugin",
        review_digest: str | None = None,
    ) -> PackageResult:
        """从 Server 的 SkillsService 获取并打包已注册的技能

        Args:
            skill_id: 技能 ID
            preview_only: 如果为 True，仅返回脱敏预览结果与文件树摘要，不实际生成 ZIP
            apply_redactions: 如果为 True，将脱敏后的内容写入 ZIP；否则写入原始内容（用户确认无误或忽略警告）
            ignored_redactions: 字典，key 为文件名，value 为该文件中需要忽略脱敏的匹配项索引列表
            export_format: 导出格式，"agent_plugin" (Agent Plugins 1.0.0 规范，默认) 或 "raw_skill" (单技能结构)
            review_digest: 预览返回的文件树摘要。导出携带"忽略脱敏"决定（ignored_redactions 非空）时必须与当前
                文件树一致：忽略索引只对被预览的那份内容有效，技能在预览后被修改会让索引指向另一处密钥。
                仅 apply_redactions（脱敏全部命中项）是单向收紧，无需摘要
        """
        try:
            skill = await self._skills_svc.get_skill(skill_id)
            if not skill:
                return PackageResult(
                    success=False,
                    zip_content=None,
                    filename=None,
                    error=f"Skill not found: {skill_id}",
                )

            # 从 evolution 存储读取回归门禁快照与真实演化版本
            eval_cases_count = 0
            lineage_version: int | None = None
            record = _load_evolution_record(skill.name)
            if record is not None:
                eval_cases_count = len(record.eval_cases or [])
                lineage_version = record.lineage.version

            collected = await collect_skill_files(self._skills_svc, skill_id, lineage_version=lineage_version)
            if not collected:
                return PackageResult(success=False, zip_content=None, filename=None, error="Skill has no files")

            current_digest = compute_review_digest(collected)
            keeps_findings = any(ignored_redactions.values()) if ignored_redactions else False
            if keeps_findings and not preview_only and review_digest != current_digest:
                return PackageResult(
                    success=False,
                    zip_content=None,
                    filename=None,
                    error="The skill changed since the redaction preview; review the findings again.",
                    error_code=SKILL_CHANGED_SINCE_PREVIEW,
                    review_digest=current_digest,
                )

            # 扫描是 CPU 密集型（~1 s/MB），放到线程池避免阻塞事件循环
            outcome = await asyncio.to_thread(
                redact_files,
                collected,
                apply=apply_redactions,
                ignored=ignored_redactions,
            )
            file_contents = outcome.files
            all_redactions = outcome.redactions

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
                file_contents[EVALS_FILE] = evals_sanitized.sanitized_content.encode("utf-8")

            if preview_only:
                return PackageResult(
                    success=True,
                    zip_content=None,
                    filename=None,
                    redactions=all_redactions or None,
                    is_safe=outcome.is_safe,
                    eval_cases_count=eval_cases_count,
                    review_digest=current_digest,
                )

            # Actual packaging: 根据 export_format 选择打包规范
            version_str = str(lineage_version) if lineage_version is not None else (skill.version or "1.0.0")
            if export_format == "raw_skill":
                pack_result = self._packer.package_files(skill.name, version_str, file_contents)
            else:
                extra_ext = None
                if eval_cases_count > 0:
                    extra_ext = {
                        "ai.myrm.evals": {
                            "evalCasesCount": eval_cases_count,
                            "hasEvalsSnapshot": True,
                        }
                    }
                pack_result = self._packer.package_as_agent_plugin(
                    skill_name=skill.name,
                    version=version_str,
                    file_contents=file_contents,
                    description=getattr(skill, "description", None),
                    keywords=getattr(skill, "tags", None),
                    extra_extensions=extra_ext,
                )

            # Wrap the harness result to include redaction info
            return PackageResult(
                success=pack_result.success,
                zip_content=pack_result.zip_content,
                filename=pack_result.filename,
                error=pack_result.error,
                redactions=all_redactions or None,
                is_safe=outcome.is_safe,
                eval_cases_count=eval_cases_count,
                review_digest=current_digest,
            )

        except Exception as e:
            logger.error(f"Failed to package skill {skill_id}: {e}")
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
            return PackageResult(
                success=False,
                zip_content=None,
                filename=None,
                error=f"未找到会话 {chat_id} 的工作空间",
            )

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
            if not is_evals_file(key):
                continue
            raw = files.pop(key)
            parsed = parse_evals_json(raw)
            if parsed is None:
                logger.warning("Skill %s: ignoring invalid %s", info.name, key)
            elif eval_cases is None:
                eval_cases = parsed

        if not force:
            existing_skills = await self._skills_svc.list_skills()
            for skill in existing_skills:
                if skill.name == info.name:
                    return UnpackResult(
                        success=False,
                        error=f"Skill already exists: {info.name}, use force=true to overwrite",
                    )

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
            logger.info("Skill registered: %s (%s)", skill.id, info.name)
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
            record.updated_at = datetime.now()
            await store.save_skill(record)
            return len(eval_cases)
        except Exception as exc:
            logger.warning("Failed to restore eval_cases for '%s': %s", skill.name, exc)
            return 0


skill_packaging_service = SkillPackagingService()

__all__ = [
    "SKILL_CHANGED_SINCE_PREVIEW",
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
