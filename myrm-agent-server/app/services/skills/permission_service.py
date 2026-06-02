"""Skill Permission Service

业务层的权限检查服务，连接数据库和框架层验证逻辑。
提供permission checker factory，供Agent运行时使用。

包含per-session权限缓存，避免每次tool call都查数据库。
"""

import logging
from collections.abc import Awaitable, Callable

from myrm_agent_harness.backends.skills import (
    SkillPermission,
    check_permission_for_tool_call,
    log_permission_usage,
)
from sqlalchemy import select

from app.database.connection import get_session
from app.database.models import SkillPermissionGrant

logger = logging.getLogger(__name__)

# Per-session permission cache
# Key: skill_id, Value: set[SkillPermission]
_permission_cache: dict[str, set[SkillPermission]] = {}


async def load_granted_permissions(skill_id: str) -> set[SkillPermission]:
    """从数据库加载授予的权限（无缓存）

    Args:
        skill_id: Skill ID

    Returns:
        已授予的SkillPermission集合
    """
    async with get_session() as db:
        stmt = select(SkillPermissionGrant).where(
            SkillPermissionGrant.skill_id == skill_id,
        )
        result = await db.execute(stmt)
        grants = result.scalars().all()

        # Convert permission strings to SkillPermission enum
        permissions = set()
        for grant in grants:
            try:
                perm = SkillPermission(grant.permission)
                permissions.add(perm)
            except ValueError:
                logger.warning(f"Invalid permission in database: {grant.permission}, skipping")

        return permissions


async def load_granted_permissions_cached(skill_id: str) -> set[SkillPermission]:
    """从缓存或数据库加载授予的权限

    使用per-session缓存，避免每次tool call都查数据库。
    缓存在grant/revoke时会被清空。

    Args:
        skill_id: Skill ID

    Returns:
        已授予的SkillPermission集合
    """
    # Check cache first
    if skill_id in _permission_cache:
        logger.debug(f"Permission cache hit: skill={skill_id}")
        return _permission_cache[skill_id]

    # Cache miss - load from database
    logger.debug(f"Permission cache miss: skill={skill_id}")
    permissions = await load_granted_permissions(skill_id)

    # Store in cache
    _permission_cache[skill_id] = permissions

    return permissions


def clear_permission_cache(skill_id: str | None = None) -> None:
    """清空权限缓存

    在grant/revoke权限后调用，确保缓存一致性。

    Args:
        skill_id: Skill ID（None表示清空所有Skill）
    """
    if skill_id is None:
        # Clear all cache
        _permission_cache.clear()
        logger.info("Cleared all permission cache")
    else:
        # Clear specific skill
        if skill_id in _permission_cache:
            del _permission_cache[skill_id]
            logger.info(f"Cleared permission cache: skill={skill_id}")
        else:
            logger.debug(f"Permission cache not found: skill={skill_id}")


def create_permission_checker() -> Callable[[str, str, str], tuple[bool, str]]:
    """创建permission checker函数（同步版本，用于middleware）

    返回一个可供Agent使用的permission checker函数。
    该函数会查询数据库、调用框架层验证、记录日志。

    注意：由于middleware的on_tool_start是同步的，这里提供同步接口。
    内部使用asyncio.run执行异步操作（Python 3.7+推荐方式）。

    Returns:
        Permission checker函数: (skill_id, permission_type, operation) -> (allowed, reason)

    Usage:
        checker = create_permission_checker()
        allowed, reason = checker(skill_id, "file_write", "/path/to/file")
    """

    def checker(skill_id: str, permission_type: str, operation: str) -> tuple[bool, str]:
        """检查权限（同步包装）

        Args:
            skill_id: Skill ID
            permission_type: 权限类型（如 "file_write", "shell_exec"）
            operation: 操作描述（如文件路径、命令）

        Returns:
            (allowed, reason) - 是否允许 + 拒绝原因（如果拒绝）
        """
        import asyncio

        async def _async_check() -> tuple[bool, str]:
            # 加载授予的权限（使用缓存）
            granted_perms = await load_granted_permissions_cached(skill_id)

            # 调用框架层验证
            allowed, reason = check_permission_for_tool_call(permission_type, granted_perms)

            # 记录日志
            log_permission_usage(skill_id, permission_type, operation, allowed, reason)

            return allowed, reason

        # 使用asyncio.run（Python 3.7+推荐方式）
        return asyncio.run(_async_check())

    return checker


async def create_async_permission_checker() -> Callable[[str, str, str], Awaitable[tuple[bool, str]]]:
    """创建异步permission checker函数

    Returns:
        Async permission checker: async (skill_id, permission_type, operation) -> (allowed, reason)
    """

    async def async_checker(skill_id: str, permission_type: str, operation: str) -> tuple[bool, str]:
        """异步检查权限"""
        # 加载授予的权限
        granted_perms = await load_granted_permissions(skill_id)

        # 调用框架层验证
        allowed, reason = check_permission_for_tool_call(permission_type, granted_perms)

        # 记录日志
        log_permission_usage(skill_id, permission_type, operation, allowed, reason)

        return allowed, reason

    return async_checker


__all__ = [
    "load_granted_permissions",
    "create_permission_checker",
    "create_async_permission_checker",
]
