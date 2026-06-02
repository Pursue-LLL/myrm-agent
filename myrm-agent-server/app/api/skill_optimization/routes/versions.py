from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

if TYPE_CHECKING:
    from myrm_agent_harness.agent.skills.optimization.types import SkillVersion

from fastapi import APIRouter, Depends, HTTPException
from myrm_agent_harness.agent.skills.optimization import EventEmitter
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.skill_optimization.sqlalchemy_storage import SQLAlchemyStorage
from app.api.skill_optimization.dependencies import (
    get_event_emitter,
    get_storage,
)
from app.database.connection import get_db

router = APIRouter()

@router.get("/versions/{skill_id}")
async def list_skill_versions(
    skill_id: str,
    storage: Annotated[SQLAlchemyStorage, Depends(get_storage)],
    limit: int = 50,
) -> dict[str, object]:
    """获取skill的所有版本

    Args:
        skill_id: Skill ID
        limit: 返回数量限制

    Returns:
        版本列表（按版本号倒序）
    """
    versions = await storage.list_skill_versions(skill_id, limit)

    return {
        "skill_id": skill_id,
        "total": len(versions),
        "versions": [
            {
                "version": v.version,
                "created_at": v.created_at.isoformat(),
                "created_by": v.created_by,
                "is_active": v.is_active,
                "optimization_id": v.optimization_id,
                "quality_score": {
                    "overall_score": v.quality_score.overall_score,
                    "success_rate": v.quality_score.success_rate,
                    "token_efficiency": v.quality_score.token_efficiency,
                    "execution_time": v.quality_score.execution_time,
                    "user_satisfaction": v.quality_score.user_satisfaction,
                    "call_frequency": v.quality_score.call_frequency,
                }
                if v.quality_score
                else None,
                "metadata": v.metadata,
            }
            for v in versions
        ],
    }

@router.get("/versions/{skill_id}/compare")
async def compare_skill_versions(
    skill_id: str,
    v1: int,
    v2: int,
    storage: Annotated[SQLAlchemyStorage, Depends(get_storage)],
) -> dict[str, object]:
    """比较两个版本

    Args:
        skill_id: Skill ID
        v1: 第一个版本号（query param）
        v2: 第二个版本号（query param）

    Returns:
        两个版本的详情对比数据
    """
    version_1 = await storage.get_skill_version(skill_id, v1)
    version_2 = await storage.get_skill_version(skill_id, v2)

    if not version_1:
        raise HTTPException(status_code=404, detail=f"Version {v1} not found")
    if not version_2:
        raise HTTPException(status_code=404, detail=f"Version {v2} not found")

    def _version_summary(v: "SkillVersion") -> dict[str, object]:
        return {
            "version": v.version,
            "created_at": v.created_at.isoformat(),
            "created_by": v.created_by,
            "is_active": v.is_active,
            "content": v.content,
            "quality_score": {
                "overall_score": v.quality_score.overall_score,
                "success_rate": v.quality_score.success_rate,
                "token_efficiency": v.quality_score.token_efficiency,
                "execution_time": v.quality_score.execution_time,
                "user_satisfaction": v.quality_score.user_satisfaction,
                "call_frequency": v.quality_score.call_frequency,
            }
            if v.quality_score
            else None,
        }

    score_delta = None
    if version_1.quality_score and version_2.quality_score:
        score_delta = {
            "overall_score": version_2.quality_score.overall_score - version_1.quality_score.overall_score,
            "success_rate": version_2.quality_score.success_rate - version_1.quality_score.success_rate,
            "token_efficiency": version_2.quality_score.token_efficiency - version_1.quality_score.token_efficiency,
            "execution_time": version_2.quality_score.execution_time - version_1.quality_score.execution_time,
            "user_satisfaction": version_2.quality_score.user_satisfaction - version_1.quality_score.user_satisfaction,
        }

    return {
        "skill_id": skill_id,
        "v1": _version_summary(version_1),
        "v2": _version_summary(version_2),
        "score_delta": score_delta,
        "content_changed": version_1.content != version_2.content,
    }

@router.get("/versions/{skill_id}/{version}")
async def get_skill_version_detail(
    skill_id: str,
    version: int,
    storage: Annotated[SQLAlchemyStorage, Depends(get_storage)],
) -> dict[str, object]:
    """获取skill指定版本的详情（含内容）

    Args:
        skill_id: Skill ID
        version: 版本号

    Returns:
        版本详情（含content）
    """
    sv = await storage.get_skill_version(skill_id, version)
    if not sv:
        raise HTTPException(
            status_code=404,
            detail=f"Version {version} not found for skill {skill_id}",
        )

    return {
        "skill_id": sv.skill_id,
        "version": sv.version,
        "content": sv.content,
        "created_at": sv.created_at.isoformat(),
        "created_by": sv.created_by,
        "is_active": sv.is_active,
        "optimization_id": sv.optimization_id,
        "quality_score": {
            "overall_score": sv.quality_score.overall_score,
            "success_rate": sv.quality_score.success_rate,
            "token_efficiency": sv.quality_score.token_efficiency,
            "execution_time": sv.quality_score.execution_time,
            "user_satisfaction": sv.quality_score.user_satisfaction,
            "call_frequency": sv.quality_score.call_frequency,
        }
        if sv.quality_score
        else None,
        "metadata": sv.metadata,
    }

@router.post("/rollback/{skill_id}")
async def rollback_optimization(
    skill_id: str,
    target_version: int,
    storage: Annotated[SQLAlchemyStorage, Depends(get_storage)],
    event_emitter: Annotated[EventEmitter, Depends(get_event_emitter)],
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    """版本回滚API，激活指定的历史版本。"""
    # 检查目标版本是否存在
    target_skill_version = await storage.get_skill_version(skill_id, target_version)
    if not target_skill_version:
        raise HTTPException(
            status_code=404,
            detail=f"Target version {target_version} not found for skill {skill_id}",
        )

    # 获取当前激活版本（用于审计日志）
    current_active = await storage.get_active_version(skill_id)
    current_version = current_active.version if current_active else None

    # 激活目标版本
    await storage.activate_version(skill_id, target_version)

    # 记录审计日志
    from datetime import datetime

    audit_log = {
        "skill_id": skill_id,
        "action": "rollback",
        "from_version": current_version,
        "to_version": target_version,
        "timestamp": datetime.now().isoformat(),
        "triggered_by": "manual",  # 实际应从认证信息获取user_id
    }

    # 发射回滚事件（用于WebSocket通知）
    await event_emitter.emit(
        "version_rollback",
        {
            "skill_id": skill_id,
            "from_version": current_version,
            "to_version": target_version,
        },
    )

    return {
        "message": f"Successfully rolled back {skill_id} to version {target_version}",
        "skill_id": skill_id,
        "from_version": current_version,
        "to_version": target_version,
        "audit_log": audit_log,
    }

