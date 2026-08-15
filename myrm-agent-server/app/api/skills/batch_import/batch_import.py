"""批量导入 (GUI-First 技能迁移) 接口.

处理从前端上传的 ZIP，进行安全解压与冲突预览。
用户确认策略后，落盘到 Sandbox 的 SkillStore 中。

[INPUT]
- POST skills batch-import multipart ZIP upload（前端 GUI 触发）.
- HermesBatchParser（myrm_agent_harness）解析技能包.

[OUTPUT]
- 安全解压 + 冲突预览；用户确认策略后落盘 Sandbox SkillStore.

[POS]
Server business layer (Skills API). GUI-First skill migration entrypoint:
ZIP → safe extract → conflict preview → confirmed install to SkillStore.
"""

from __future__ import annotations

import logging
import uuid
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, UploadFile
from myrm_agent_harness.agent.skills.market.installers.batch_installer import (
    HermesBatchParser,
)
from myrm_agent_harness.backends.skills.scanning.archive_security import (
    classify_archive_security_issue,
)

from app.api.skills._deploy_capability import require_local_skills_capability
from app.api.skills.evolution.helpers import _get_skill_store

from .batch_import_execute import execute_batch_import_confirm
from .batch_import_helpers import (
    _build_batch_import_error_detail,
    _resolve_batch_import_error_message,
)
from .batch_import_schemas import (
    ConfirmImportRequest,
    ConfirmImportResponse,
    ImportPreviewResponse,
    ImportPreviewSkillItem,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/batch-import", tags=["skills-batch-import"])


@router.post("/preview", response_model=ImportPreviewResponse)
async def preview_batch_import(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
) -> ImportPreviewResponse:
    """接收ZIP并返回带冲突标记的技能预览列表"""
    require_local_skills_capability()
    if not file.filename or not file.filename.endswith(".zip"):
        raise HTTPException(status_code=400, detail="必须上传 .zip 文件")

    zip_bytes = await file.read()
    if not zip_bytes:
        raise HTTPException(status_code=400, detail="文件为空")

    if len(zip_bytes) > 10 * 1024 * 1024:
        raise HTTPException(
            status_code=400,
            detail="上传被系统安全拦截：文件大小不能超过 10MB，保护内存免遭拒绝服务攻击。",
        )

    parser = HermesBatchParser()
    try:
        imported_skills = parser.parse_zip(zip_bytes)
    except Exception as e:
        violation = classify_archive_security_issue(e)
        detail = _resolve_batch_import_error_message(e, violation=violation)
        payload = _build_batch_import_error_detail(detail, violation=violation)
        if violation is not None:
            logger.warning(
                "Batch import blocked by archive security policy: %s", detail
            )
        else:
            logger.error(f"Failed to parse ZIP: {e}")
        raise HTTPException(
            status_code=400,
            detail=payload,
        ) from e

    if not imported_skills:
        return ImportPreviewResponse(
            session_id="", items=[], total_found=0, total_conflicts=0
        )

    store = _get_skill_store()

    # 初始化暂存区和安全扫描器
    from app.api.skills._staging import SkillStagingManager

    staging_manager = SkillStagingManager(store.db_path.parent)

    try:
        from app.api.skills.optimization.config import SecurityConfig
        from app.api.skills.optimization.security import SkillSecurityValidator

        validator = SkillSecurityValidator(config=SecurityConfig())
    except ImportError:
        from myrm_agent_harness.agent.skills.optimization.config import SecurityConfig
        from myrm_agent_harness.agent.skills.optimization.security import (
            SkillSecurityValidator,
        )

        validator = SkillSecurityValidator(config=SecurityConfig())

    if hasattr(store, "list_skills"):
        existing_skills = store.list_skills()
    else:
        existing_skills = store.get_active_skills()
    existing_map = {s.name: s.skill_id for s in existing_skills}

    preview_items = []
    total_conflicts = 0
    session_id = uuid.uuid4().hex

    for i, skill in enumerate(imported_skills):
        virtual_id = f"import_{i}"
        conflict_type: Literal["none", "conflict"] = "none"
        existing_id = None
        security_issues = None

        # 前置安全扫描
        val_result = validator.validate_skill(
            f"---\nname: {skill.name}\ndescription: {skill.description}\n---\n{skill.content}"
        )
        if not val_result.passed:
            security_issues = "; ".join(val_result.issues)

        if skill.name in existing_map:
            conflict_type = "conflict"
            existing_id = existing_map[skill.name]
            total_conflicts += 1

        preview_items.append(
            ImportPreviewSkillItem(
                name=skill.name,
                description=skill.description,
                conflict_type=conflict_type,
                existing_skill_id=existing_id,
                virtual_id=virtual_id,
                security_issues=security_issues,
            )
        )

    # 持久化保存到暂存区，解决多文件丢失和前端 OOM 问题
    staging_manager.save_session(session_id, imported_skills)

    # 异步触发全局垃圾回收，不阻塞当前请求
    background_tasks.add_task(staging_manager._cleanup_expired_sessions_sync)

    return ImportPreviewResponse(
        session_id=session_id,
        items=preview_items,
        total_found=len(preview_items),
        total_conflicts=total_conflicts,
    )


@router.post("/confirm", response_model=ConfirmImportResponse)
async def confirm_batch_import(
    request: ConfirmImportRequest,
    background_tasks: BackgroundTasks,
) -> ConfirmImportResponse:
    """确认导入策略并落盘"""
    require_local_skills_capability()
    store = _get_skill_store()
    from app.api.skills._staging import SkillStagingManager

    staging_manager = SkillStagingManager(store.db_path.parent)

    try:
        imported_skills = staging_manager.load_session(request.session_id)
    except Exception as e:
        violation = classify_archive_security_issue(e)
        detail = (
            _resolve_batch_import_error_message(e, violation=violation)
            if violation is not None
            else str(e)
        )
        if not detail.strip():
            detail = "导入会话无效或已过期。"
        payload = _build_batch_import_error_detail(detail, violation=violation)
        if violation is not None:
            logger.warning(
                "Batch import confirm blocked by archive security policy: %s", detail
            )
        else:
            logger.error("Batch import confirm failed to load session: %s", e)
        raise HTTPException(status_code=400, detail=payload) from e

    # 引入安全扫描器
    try:
        from app.api.skills.optimization.config import SecurityConfig
        from app.api.skills.optimization.security import SkillSecurityValidator

        validator = SkillSecurityValidator(config=SecurityConfig())
    except ImportError:
        # Fallback to harness if imported there
        from myrm_agent_harness.agent.skills.optimization.config import SecurityConfig
        from myrm_agent_harness.agent.skills.optimization.security import (
            SkillSecurityValidator,
        )

        validator = SkillSecurityValidator(config=SecurityConfig())

    try:
        imported_count, skipped_count, restored_eval_cases = (
            await execute_batch_import_confirm(
                request,
                store=store,
                staging_manager=staging_manager,
                validator=validator,
                imported_skills=imported_skills,
            )
        )
    finally:
        # 无论成功失败，都清理暂存区，保证磁盘 0 冗余
        staging_manager.cleanup_session(request.session_id)
        # 异步触发全局垃圾回收，不阻塞当前请求
        background_tasks.add_task(staging_manager._cleanup_expired_sessions_sync)

    return ConfirmImportResponse(
        imported_count=imported_count,
        skipped_count=skipped_count,
        restored_eval_cases=restored_eval_cases,
    )
