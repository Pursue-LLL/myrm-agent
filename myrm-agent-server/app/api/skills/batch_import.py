"""批量导入 (GUI-First 技能迁移) 接口

处理从前端上传的 ZIP，进行安全解压与冲突预览。
用户确认策略后，落盘到 Sandbox 的 SkillStore 中。
"""

from __future__ import annotations

import io
import logging
import uuid
from typing import Literal

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from app.api.skills.evolution.helpers import _get_skill_store
from myrm_agent_harness.agent.skills.discovery.installers.batch_installer import (
    HermesBatchParser,
)
from myrm_agent_harness.agent.skills.evolution.core.types import (
    EvolutionType,
    SkillLineage,
    SkillRecord,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/batch-import", tags=["skills-batch-import"])


class ImportPreviewSkillItem(BaseModel):
    name: str
    description: str
    conflict_type: Literal["none", "conflict"]
    existing_skill_id: str | None = None
    # 将 ZIP 中的相对路径作为内部索引
    virtual_id: str
    # 新增前置安全扫描结果
    security_issues: str | None = None


class ImportPreviewResponse(BaseModel):
    session_id: str
    items: list[ImportPreviewSkillItem]
    total_found: int
    total_conflicts: int


class ConfirmImportItem(BaseModel):
    virtual_id: str
    name: str
    description: str
    resolution: Literal["replace", "rename_cow", "skip", "new"]
    existing_skill_id: str | None = None


class ConfirmImportRequest(BaseModel):
    session_id: str
    items: list[ConfirmImportItem]


class ConfirmImportResponse(BaseModel):
    imported_count: int
    skipped_count: int


@router.post("/preview", response_model=ImportPreviewResponse)
async def preview_batch_import(
    file: UploadFile = File(...),
) -> ImportPreviewResponse:
    """接收ZIP并返回带冲突标记的技能预览列表"""
    if not file.filename or not file.filename.endswith(".zip"):
        raise HTTPException(status_code=400, detail="必须上传 .zip 文件")
        
    zip_bytes = await file.read()
    if not zip_bytes:
        raise HTTPException(status_code=400, detail="文件为空")
        
    if len(zip_bytes) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="上传被系统安全拦截：文件大小不能超过 10MB，保护内存免遭拒绝服务攻击。")
        
    parser = HermesBatchParser()
    try:
        imported_skills = parser.parse_zip(zip_bytes)
    except Exception as e:
        logger.error(f"Failed to parse ZIP: {e}")
        raise HTTPException(status_code=400, detail=f"解析压缩包失败，防爆防护触发或格式错误: {e}")
        
    if not imported_skills:
        return ImportPreviewResponse(session_id="", items=[], total_found=0, total_conflicts=0)
        
    store = _get_skill_store()
    
    # 初始化暂存区和安全扫描器
    from app.api.skills._staging import SkillStagingManager
    staging_manager = SkillStagingManager(store.db_path.parent)
    
    try:
        from app.api.skills.optimization.security import SkillSecurityValidator
        from app.api.skills.optimization.config import SecurityConfig
        validator = SkillSecurityValidator(config=SecurityConfig())
    except ImportError:
        from myrm_agent_harness.agent.skills.optimization.security import SkillSecurityValidator
        from myrm_agent_harness.agent.skills.optimization.config import SecurityConfig
        validator = SkillSecurityValidator(config=SecurityConfig())
        
    existing_skills = store.list_skills()
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
        val_result = validator.validate_skill(f"---\nname: {skill.name}\ndescription: {skill.description}\n---\n{skill.content}")
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
        
    return ImportPreviewResponse(
        session_id=session_id,
        items=preview_items,
        total_found=len(preview_items),
        total_conflicts=total_conflicts,
    )


@router.post("/confirm", response_model=ConfirmImportResponse)
async def confirm_batch_import(
    request: ConfirmImportRequest,
) -> ConfirmImportResponse:
    """确认导入策略并落盘"""
    store = _get_skill_store()
    from app.api.skills._staging import SkillStagingManager
    staging_manager = SkillStagingManager(store.db_path.parent)
    
    try:
        imported_skills = staging_manager.load_session(request.session_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    # 引入安全扫描器
    try:
        from app.api.skills.optimization.security import SkillSecurityValidator
        from app.api.skills.optimization.config import SecurityConfig
        validator = SkillSecurityValidator(config=SecurityConfig())
    except ImportError:
        # Fallback to harness if imported there
        from myrm_agent_harness.agent.skills.optimization.security import SkillSecurityValidator
        from myrm_agent_harness.agent.skills.optimization.config import SecurityConfig
        validator = SkillSecurityValidator(config=SecurityConfig())
    
    imported_count = 0
    skipped_count = 0
    
    # Phase 1: 安全预检 (Defense-in-depth, 拦截恶意请求)
    for item in request.items:
        if item.resolution == "skip":
            continue
            
        try:
            skill_idx = int(item.virtual_id.split("_")[1])
            skill = imported_skills[skill_idx]
        except (IndexError, ValueError, KeyError):
            raise HTTPException(status_code=400, detail="非法的 virtual_id")
            
        val_result = validator.validate_skill(f"---\nname: {item.name}\ndescription: {item.description}\n---\n{skill.content}")
        if not val_result.passed:
            logger.warning(f"Skill {item.name} failed security scan during confirm: {val_result.issues}")
            # 立即清理暂存区并阻断
            staging_manager.cleanup_session(request.session_id)
            raise HTTPException(status_code=400, detail=f"安全拦截: {item.name} 包含恶意代码 -> {val_result.issues}。本次导入已撤销。")

    # Phase 2: 落盘暂存与数据库更新 (全保真原子写入)
    temp_files = []
    try:
        import os
        from pathlib import Path
        
        for item in request.items:
            if item.resolution == "skip":
                skipped_count += 1
                continue
                
            skill_idx = int(item.virtual_id.split("_")[1])
            skill = imported_skills[skill_idx]
                
            skill_id = str(uuid.uuid4())
            name = item.name
            evolution_type = EvolutionType.FIX # default
            parent_id = None
            
            if item.resolution == "replace" and item.existing_skill_id:
                # 覆盖：更新原技能
                skill_id = item.existing_skill_id
                evolution_type = EvolutionType.DERIVED
                parent_id = skill_id
            elif item.resolution == "rename_cow":
                name = f"{item.name}_copy"
                evolution_type = EvolutionType.DERIVED
                parent_id = item.existing_skill_id
            
            # 构建完整写入路径，Sandbox 模式中通常存储到 data_dir/skills/<uuid>
            skill_dir = store.db_path.parent / "skills" / skill_id
            skill_dir.mkdir(parents=True, exist_ok=True)
            path = str(skill_dir / "SKILL.md")
            
            record = SkillRecord(
                skill_id=skill_id,
                name=name,
                description=item.description,
                content=skill.content,
                path=path,
                lineage=SkillLineage(
                    evolution_type=evolution_type,
                    version=1,
                    parent_id=parent_id,
                    change_summary="Migrated via Hermes Batch Import",
                    created_by="human"
                )
            )
            
            # 多文件全保真原子写入：为所有 file 生成 .tmp
            for rel_path, file_content in skill.files.items():
                if rel_path == "SKILL.md":
                    # 对于 SKILL.md，我们要注入更新后的 name 和 description (Frontmatter)
                    file_content = f"---\nname: {name}\ndescription: {item.description}\n---\n{skill.content}".encode("utf-8")
                    
                target_path = skill_dir / rel_path
                target_path.parent.mkdir(parents=True, exist_ok=True)
                
                tmp_path = str(target_path) + f".{uuid.uuid4().hex}.tmp"
                with open(tmp_path, "wb") as f:
                    f.write(file_content)
                temp_files.append((tmp_path, str(target_path)))
            
            # DB 写库，若失败将抛出异常
            await store.save_skill(record)
            imported_count += 1
            
        # Phase 3: 全部 DB 提交成功后，在操作系统底层执行原子物理替换
        for tmp_path, final_path in temp_files:
            os.replace(tmp_path, final_path)
            
    except Exception as e:
        # 回滚：全量清空本次产生的所有临时文件，拒绝脏写残留
        import os
        for tmp_path, _ in temp_files:
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
        staging_manager.cleanup_session(request.session_id)
        raise e
    finally:
        # 无论成功失败，都清理暂存区，保证磁盘 0 冗余
        staging_manager.cleanup_session(request.session_id)
        
    return ConfirmImportResponse(
        imported_count=imported_count,
        skipped_count=skipped_count
    )
