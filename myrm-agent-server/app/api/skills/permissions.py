"""Skill Permission Management API

Handles skill permission approval and management.

Endpoints:
- GET /users/{user_id}/skills/{skill_id}/permissions - 查询Skill权限
- POST /users/{user_id}/skills/{skill_id}/permissions/grant - 授予权限
- POST /users/{user_id}/skills/{skill_id}/permissions/revoke - 撤销权限
- POST /users/{user_id}/skills/{skill_id}/permissions/apply-template - 应用权限模板（批量授予）
- POST /users/{user_id}/permissions/bulk-revoke-by-type - 批量撤销权限类型（所有Skill）
- GET /users/{user_id}/skills/{skill_id}/permissions/required - 查询Skill声明的required_permissions
- GET /users/{user_id}/skills/{skill_id}/permissions/usage - 查询权限使用统计
"""

import logging
from datetime import datetime, timedelta
from typing import cast

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db_session
from app.core.skills.store.service import skills_service
from app.database.models import SkillPermissionGrant, SkillPermissionUsageLog

logger = logging.getLogger(__name__)

router = APIRouter()


def _as_int(val: object, default: int = 0) -> int:
    if isinstance(val, int):
        return val
    if isinstance(val, float):
        return int(val)
    if isinstance(val, str) and val.isdigit():
        return int(val)
    return default


def _required_permission_values(skill: object) -> list[str]:
    req = getattr(skill, "required_permissions", None)
    if not req:
        return []
    out: list[str] = []
    for p in req:
        val = getattr(p, "value", None)
        out.append(str(val) if val is not None else str(p))
    return out


class SkillPermissionInfo(BaseModel):
    """Skill权限信息"""

    permission: str
    granted_at: str | None = None


class SkillPermissionsResponse(BaseModel):
    """Skill权限响应"""

    skill_id: str
    skill_name: str
    required_permissions: list[str]
    granted_permissions: list[SkillPermissionInfo]


class GrantPermissionsRequest(BaseModel):
    """授予权限请求"""

    permissions: list[str] = Field(..., description="要授予的权限列表")


class GrantPermissionsResponse(BaseModel):
    """授予权限响应"""

    skill_id: str
    granted_permissions: list[str]
    success: bool


class RevokePermissionsRequest(BaseModel):
    """撤销权限请求"""

    permissions: list[str] = Field(..., description="要撤销的权限列表")


class RevokePermissionsResponse(BaseModel):
    """撤销权限响应"""

    skill_id: str
    revoked_permissions: list[str]
    success: bool


class ApplyTemplateRequest(BaseModel):
    """应用权限模板请求"""

    template: str = Field(..., description="权限模板名称（如developer_tools）")


class ApplyTemplateResponse(BaseModel):
    """应用权限模板响应"""

    skill_id: str
    template_applied: str
    granted_permissions: list[str]
    success: bool


class BulkRevokeByTypeRequest(BaseModel):
    """批量撤销权限类型请求"""

    permission_type: str = Field(..., description="要批量撤销的权限类型（如shell_exec）")


class BulkRevokeByTypeResponse(BaseModel):
    """批量撤销权限类型响应"""

    permission_type: str
    affected_skills: list[str]
    total_revoked: int
    success: bool


@router.get("/{skill_id}/permissions", response_model=SkillPermissionsResponse)
async def get_skill_permissions(
    skill_id: str,
    db: AsyncSession = Depends(get_db_session),
) -> SkillPermissionsResponse:
    """查询Skill的权限信息（required + granted）"""
    skill = await skills_service.get_skill(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill not found: {skill_id}")

    stmt = select(SkillPermissionGrant).where(SkillPermissionGrant.skill_id == skill_id)
    result = await db.execute(stmt)
    grants = result.scalars().all()

    return SkillPermissionsResponse(
        skill_id=skill_id,
        skill_name=skill.name,
        required_permissions=_required_permission_values(skill),
        granted_permissions=[
            SkillPermissionInfo(
                permission=g.permission,
                granted_at=g.granted_at.isoformat(),
            )
            for g in grants
        ],
    )


@router.post("/{skill_id}/permissions/grant", response_model=GrantPermissionsResponse)
async def grant_permissions(
    skill_id: str,
    request: GrantPermissionsRequest,
    db: AsyncSession = Depends(get_db_session),
) -> GrantPermissionsResponse:
    """授予Skill权限

    用户在安装或启用Skill时，审批Skill声明的required_permissions后调用此API。
    也可用于事后授予额外权限。
    """
    skill = await skills_service.get_skill(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill not found: {skill_id}")

    from myrm_agent_harness.backends.skills.types import SkillPermission

    granted = []
    for perm_str in request.permissions:
        try:
            perm = SkillPermission(perm_str)
        except ValueError:
            logger.warning(f"Invalid permission: {perm_str}, skipping")
            continue

        stmt = select(SkillPermissionGrant).where(
            SkillPermissionGrant.skill_id == skill_id,
            SkillPermissionGrant.permission == perm.value,
        )
        result = await db.execute(stmt)
        existing = result.scalar_one_or_none()

        if not existing:
            grant = SkillPermissionGrant(
                user_id="sandbox",
                skill_id=skill_id,
                permission=perm.value,
            )
            db.add(grant)
            granted.append(perm.value)
            logger.info(f"Granted permission: user=sandbox, skill={skill_id}, permission={perm.value}")

    await db.commit()

    # Clear permission cache for this skill
    from app.services.skills.permission_service import clear_permission_cache

    clear_permission_cache(skill_id)

    return GrantPermissionsResponse(
        skill_id=skill_id,
        granted_permissions=granted,
        success=True,
    )


@router.post("/{skill_id}/permissions/revoke", response_model=RevokePermissionsResponse)
async def revoke_permissions(
    skill_id: str,
    request: RevokePermissionsRequest,
    db: AsyncSession = Depends(get_db_session),
) -> RevokePermissionsResponse:
    """撤销Skill权限

    从数据库中删除授权记录。撤销后，Skill将无法执行需要该权限的操作。
    """
    stmt = delete(SkillPermissionGrant).where(
        SkillPermissionGrant.skill_id == skill_id,
        SkillPermissionGrant.permission.in_(request.permissions),
    )
    result = await db.execute(stmt)
    await db.commit()

    rc = getattr(result, "rowcount", None)
    revoked_count = int(rc) if isinstance(rc, int) else 0
    logger.info(f"Revoked {revoked_count} permissions: user=sandbox, skill={skill_id}")

    # Clear permission cache for this skill (local cache)
    from app.services.skills.permission_service import clear_permission_cache

    clear_permission_cache(skill_id)

    # Notify framework layer to invalidate permissions (real-time revocation)
    from myrm_agent_harness.api.hooks import invalidate_permissions

    invalidate_permissions("default", skill_id)
    logger.info(f"Notified framework to invalidate permissions: user=sandbox, skill={skill_id}")

    return RevokePermissionsResponse(
        skill_id=skill_id,
        revoked_permissions=request.permissions if revoked_count > 0 else [],
        success=revoked_count > 0,
    )


@router.post("/{skill_id}/permissions/apply-template", response_model=ApplyTemplateResponse)
async def apply_permission_template(
    skill_id: str,
    request: ApplyTemplateRequest,
    db: AsyncSession = Depends(get_db_session),
) -> ApplyTemplateResponse:
    """应用权限模板（批量授予权限）

    用于快速授予一组标准权限。例如：
    - developer_tools: file_read, file_write, shell (via PermissionTemplate)
    - data_analysis: file_read, code_execute
    - readonly: file_read only

    这是用户体验优化，避免手动逐个勾选权限。
    """
    skill = await skills_service.get_skill(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill not found: {skill_id}")

    from myrm_agent_harness.backends.skills import (
        PermissionTemplate,
        get_template_permissions,
    )

    # 验证模板名称
    try:
        template = PermissionTemplate(request.template)
    except ValueError:
        valid_templates = [t.value for t in PermissionTemplate]
        raise HTTPException(
            status_code=400,
            detail=f"Invalid template: {request.template}. Valid templates: {valid_templates}",
        ) from None

    # 获取模板权限
    template_permissions = get_template_permissions(template)

    # 批量授予权限
    granted = []
    for perm in template_permissions:
        # 检查是否已存在
        stmt = select(SkillPermissionGrant).where(
            SkillPermissionGrant.skill_id == skill_id,
            SkillPermissionGrant.permission == perm.value,
        )
        result = await db.execute(stmt)
        existing = result.scalar_one_or_none()

        if not existing:
            grant = SkillPermissionGrant(
                user_id="sandbox",
                skill_id=skill_id,
                permission=perm.value,
            )
            db.add(grant)
            granted.append(perm.value)
            logger.info(
                f"Granted permission (template): user=sandbox, skill={skill_id}, "
                f"permission={perm.value}, template={template.value}"
            )

    await db.commit()

    # Clear permission cache for this skill
    from app.services.skills.permission_service import clear_permission_cache

    clear_permission_cache(skill_id)

    logger.info(
        f"Applied permission template: user=sandbox, skill={skill_id}, "
        f"template={template.value}, granted={len(granted)} permissions"
    )

    return ApplyTemplateResponse(
        skill_id=skill_id,
        template_applied=template.value,
        granted_permissions=granted,
        success=True,
    )


@router.post("/permissions/bulk-revoke-by-type", response_model=BulkRevokeByTypeResponse)
async def bulk_revoke_by_permission_type(
    request: BulkRevokeByTypeRequest,
    db: AsyncSession = Depends(get_db_session),
) -> BulkRevokeByTypeResponse:
    """批量撤销某个权限类型（所有Skill）

    用于安全响应场景：发现某个权限被滥用时，快速撤销所有Skill的该权限。
    例如：撤销所有Skill的shell_exec权限。

    这是安全增强功能，提升安全响应速度。
    """
    from myrm_agent_harness.backends.skills.types import SkillPermission

    # 验证权限类型
    try:
        perm = SkillPermission(request.permission_type)
    except ValueError:
        valid_permissions = [p.value for p in SkillPermission]
        raise HTTPException(
            status_code=400,
            detail=f"Invalid permission type: {request.permission_type}. Valid types: {valid_permissions}",
        ) from None

    # 查询所有拥有该权限的Skill
    stmt = (
        select(SkillPermissionGrant.skill_id)
        .where(
            SkillPermissionGrant.permission == perm.value,
        )
        .distinct()
    )
    result = await db.execute(stmt)
    affected_skill_ids = [row[0] for row in result.fetchall()]

    # 批量删除
    delete_stmt = delete(SkillPermissionGrant).where(
        SkillPermissionGrant.permission == perm.value,
    )
    delete_result = await db.execute(delete_stmt)
    await db.commit()

    drc = getattr(delete_result, "rowcount", None)
    total_revoked = int(drc) if isinstance(drc, int) else 0
    logger.info(
        f"Bulk revoked permission type: user=sandbox, "
        f"permission={perm.value}, affected_skills={len(affected_skill_ids)}, "
        f"total_revoked={total_revoked}"
    )

    # Clear permission cache for all affected skills
    from app.services.skills.permission_service import clear_permission_cache

    for skill_id in affected_skill_ids:
        clear_permission_cache(skill_id)

    # Notify framework layer to invalidate permissions for all affected skills
    from myrm_agent_harness.api.hooks import invalidate_permissions

    for skill_id in affected_skill_ids:
        invalidate_permissions("default", skill_id)

    logger.info(f"Notified framework to invalidate {len(affected_skill_ids)} skills' permissions")

    return BulkRevokeByTypeResponse(
        permission_type=perm.value,
        affected_skills=affected_skill_ids,
        total_revoked=total_revoked,
        success=total_revoked > 0,
    )


@router.get("/{skill_id}/permissions/required", response_model=dict)
async def get_required_permissions(skill_id: str) -> dict[str, object]:
    """查询Skill声明的required_permissions

    用于安装时显示权限审批对话框。
    """
    skill = await skills_service.get_skill(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill not found: {skill_id}")

    return {
        "skill_id": skill_id,
        "skill_name": skill.name,
        "required_permissions": _required_permission_values(skill),
        "description": skill.description,
    }


class PermissionUsageEntry(BaseModel):
    """权限使用记录"""

    permission: str
    operation: str
    allowed: bool
    deny_reason: str | None
    used_at: str


class PermissionUsageStats(BaseModel):
    """权限使用统计"""

    permission: str
    total_count: int
    allowed_count: int
    denied_count: int
    recent_operations: list[PermissionUsageEntry]


class SkillPermissionUsageResponse(BaseModel):
    """Skill权限使用响应"""

    skill_id: str
    skill_name: str
    stats: list[PermissionUsageStats]
    total_operations: int


@router.get("/{skill_id}/permissions/usage", response_model=SkillPermissionUsageResponse)
async def get_permission_usage_stats(
    skill_id: str,
    days: int = 7,
    db: AsyncSession = Depends(get_db_session),
) -> SkillPermissionUsageResponse:
    """查询Skill权限使用统计

    返回指定时间范围内的权限使用情况，包括：
    - 每个权限的总使用次数
    - 允许/拒绝次数
    - 最近的操作记录（最多10条）
    """
    skill = await skills_service.get_skill(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill not found: {skill_id}")

    since = datetime.utcnow() - timedelta(days=days)

    # 查询所有日志
    stmt = (
        select(SkillPermissionUsageLog)
        .where(
            SkillPermissionUsageLog.skill_id == skill_id,
            SkillPermissionUsageLog.used_at >= since,
        )
        .order_by(SkillPermissionUsageLog.used_at.desc())
    )
    result = await db.execute(stmt)
    logs = result.scalars().all()

    # 按权限分组统计
    stats_by_permission: dict[str, dict[str, object]] = {}
    for log in logs:
        if log.permission not in stats_by_permission:
            empty_recent: list[PermissionUsageEntry] = []
            stats_by_permission[log.permission] = {
                "permission": log.permission,
                "total_count": 0,
                "allowed_count": 0,
                "denied_count": 0,
                "recent_operations": empty_recent,
            }
        stats = stats_by_permission[log.permission]
        stats["total_count"] = _as_int(stats["total_count"]) + 1
        if log.allowed:
            stats["allowed_count"] = _as_int(stats["allowed_count"]) + 1
        else:
            stats["denied_count"] = _as_int(stats["denied_count"]) + 1

        # 每个权限保留最近10条
        recent_ops = cast(list[PermissionUsageEntry], stats["recent_operations"])
        if len(recent_ops) < 10:
            recent_ops.append(
                PermissionUsageEntry(
                    permission=log.permission,
                    operation=log.operation,
                    allowed=log.allowed,
                    deny_reason=log.deny_reason,
                    used_at=log.used_at.isoformat(),
                )
            )

    return SkillPermissionUsageResponse(
        skill_id=skill_id,
        skill_name=skill.name,
        stats=[
            PermissionUsageStats(
                permission=str(s["permission"]),
                total_count=_as_int(s["total_count"]),
                allowed_count=_as_int(s["allowed_count"]),
                denied_count=_as_int(s["denied_count"]),
                recent_operations=cast(list[PermissionUsageEntry], s["recent_operations"]),
            )
            for s in stats_by_permission.values()
        ],
        total_operations=len(logs),
    )
