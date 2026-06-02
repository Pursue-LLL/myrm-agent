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
    content: str
    conflict_type: Literal["none", "conflict"]
    existing_skill_id: str | None = None
    # 将 ZIP 中的相对路径作为内部索引
    virtual_id: str


class ImportPreviewResponse(BaseModel):
    items: list[ImportPreviewSkillItem]
    total_found: int
    total_conflicts: int


class ConfirmImportItem(BaseModel):
    virtual_id: str
    name: str
    description: str
    content: str
    resolution: Literal["replace", "rename_cow", "skip", "new"]
    existing_skill_id: str | None = None


class ConfirmImportRequest(BaseModel):
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
        return ImportPreviewResponse(items=[], total_found=0, total_conflicts=0)
        
    store = _get_skill_store()
    existing_skills = store.list_skills()
    existing_map = {s.name: s.skill_id for s in existing_skills}
    
    preview_items = []
    total_conflicts = 0
    
    for i, skill in enumerate(imported_skills):
        virtual_id = f"import_{i}"
        conflict_type: Literal["none", "conflict"] = "none"
        existing_id = None
        
        if skill.name in existing_map:
            conflict_type = "conflict"
            existing_id = existing_map[skill.name]
            total_conflicts += 1
            
        preview_items.append(
            ImportPreviewSkillItem(
                name=skill.name,
                description=skill.description,
                content=skill.content,
                conflict_type=conflict_type,
                existing_skill_id=existing_id,
                virtual_id=virtual_id,
            )
        )
        
    return ImportPreviewResponse(
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
    
    # Phase 1: 安全预检 (All or Nothing - 避免写入一半因包含恶意代码而中断，产生脏数据)
    for item in request.items:
        if item.resolution == "skip":
            continue
            
        val_result = validator.validate_skill(f"---\nname: {item.name}\ndescription: {item.description}\n---\n{item.content}")
        if not val_result.passed:
            logger.warning(f"Skill {item.name} failed security scan: {val_result.issues}")
            raise HTTPException(status_code=400, detail=f"安全扫描拦截: {item.name} 包含恶意代码 -> {val_result.issues}。本次批量导入已全量撤销保护。")

    # Phase 2: 落盘与数据库更新
    for item in request.items:
        if item.resolution == "skip":
            skipped_count += 1
            continue
            
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
        
        # 构建完整写入路径，Sandbox 模式中通常存储到 data_dir/skills
        # SkillStore 会管理这个路径的物理落盘
        path = str(store.db_path.parent / "skills" / skill_id / "SKILL.md")
        
        record = SkillRecord(
            skill_id=skill_id,
            name=name,
            description=item.description,
            content=item.content,
            path=path,
            lineage=SkillLineage(
                evolution_type=evolution_type,
                version=1,
                parent_id=parent_id,
                change_summary="Migrated via Hermes Batch Import",
                created_by="human"
            )
        )
        
        # 物理落盘与DB记录更新，利用 UoW 或 store 内置的事务
        import os
        from pathlib import Path
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"---\nname: {name}\ndescription: {item.description}\n---\n{item.content}")
            
        import asyncio
        loop = asyncio.get_event_loop()
        # save_skill is async
        await store.save_skill(record)
        imported_count += 1
        
    return ConfirmImportResponse(
        imported_count=imported_count,
        skipped_count=skipped_count
    )
