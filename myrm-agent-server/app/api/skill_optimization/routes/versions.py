from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

if TYPE_CHECKING:
    from myrm_agent_harness.agent.skills.optimization.types import SkillQualityScore, SkillVersion

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.skill_optimization.sqlalchemy_storage import SQLAlchemyStorage
from app.api.skill_optimization.dependencies import get_storage
from app.database.connection import get_db
from app.services.skills.write_orchestrator import is_neutral_quality_score

router = APIRouter()


_SCORE_DELTA_KEYS = ("overall_score", "success_rate", "token_efficiency", "execution_time", "user_satisfaction")


def _quality_score_payload(score: SkillQualityScore | None) -> dict[str, float] | None:
    if score is None or is_neutral_quality_score(score):
        return None
    return {
        "overall_score": score.overall_score,
        "success_rate": score.success_rate,
        "token_efficiency": score.token_efficiency,
        "execution_time": score.execution_time,
        "user_satisfaction": score.user_satisfaction,
        "call_frequency": score.call_frequency,
    }


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
                "quality_score": _quality_score_payload(v.quality_score),
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
            "quality_score": _quality_score_payload(v.quality_score),
        }

    score_1 = _quality_score_payload(version_1.quality_score)
    score_2 = _quality_score_payload(version_2.quality_score)
    score_delta = {key: score_2[key] - score_1[key] for key in _SCORE_DELTA_KEYS} if score_1 and score_2 else None

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
        "quality_score": _quality_score_payload(sv.quality_score),
        "metadata": sv.metadata,
    }


@router.post("/rollback/{skill_id}")
async def rollback_optimization(
    skill_id: str,
    target_version: int,
    storage: Annotated[SQLAlchemyStorage, Depends(get_storage)],
) -> dict[str, object]:
    """版本回滚API，激活指定的历史版本。"""
    # 检查目标版本是否存在
    target_skill_version = await storage.get_skill_version(skill_id, target_version)
    if not target_skill_version:
        raise HTTPException(
            status_code=404,
            detail=f"Target version {target_version} not found for skill {skill_id}",
        )

    # 记录回滚前的激活版本，供响应展示
    current_active = await storage.get_active_version(skill_id)
    current_version = current_active.version if current_active else None

    from app.services.skill_optimization.skill_version_sync import activate_version_with_disk_sync

    await activate_version_with_disk_sync(storage, skill_id, target_version)

    return {
        "message": f"Successfully rolled back {skill_id} to version {target_version}",
        "skill_id": skill_id,
        "from_version": current_version,
        "to_version": target_version,
    }


@router.post("/mutations/{batch_id}/rollback")
async def rollback_skill_mutation_batch_route(
    batch_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str | int]:
    from app.services.skills.mutation_batch_service import (
        MutationBatchAlreadyConsumedError,
        MutationBatchCompensationError,
        MutationBatchRollbackError,
        rollback_skill_mutation_batch,
    )

    try:
        restored = await rollback_skill_mutation_batch(db, batch_id)
        await db.commit()
    except MutationBatchAlreadyConsumedError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail={"code": "batch_already_consumed", "message": str(exc)},
        ) from exc
    except MutationBatchCompensationError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail={"code": "compensation_failed", "message": str(exc)},
        ) from exc
    except MutationBatchRollbackError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail={"code": "rollback_failed", "message": str(exc)},
        ) from exc
    return {"batch_id": batch_id, "skills_restored": restored, "status": "rolled_back"}


@router.get("/package-revisions/{skill_id}")
async def list_package_revisions(
    skill_id: str,
    db: AsyncSession = Depends(get_db),
    limit: int = 50,
) -> dict[str, object]:
    from app.services.skills.package_revision_service import list_package_revisions as list_rows

    rows = await list_rows(db, skill_id, limit=limit)
    return {
        "skill_id": skill_id,
        "revisions": [
            {
                "revision_number": r.revision_number,
                "revision_id": r.revision_id,
                "created_by": r.created_by,
                "resource_paths": r.resource_paths,
            }
            for r in rows
        ],
    }


@router.post("/package-revisions/{skill_id}/restore/{revision_number}")
async def restore_package_revision_route(
    skill_id: str,
    revision_number: int,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str | int]:
    from app.services.skills.package_revision_service import (
        PackageRevisionRestoreError,
        restore_package_revision,
    )

    try:
        await restore_package_revision(db, skill_id, revision_number)
        await db.commit()
    except PackageRevisionRestoreError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"skill_id": skill_id, "revision_number": revision_number, "status": "restored"}
