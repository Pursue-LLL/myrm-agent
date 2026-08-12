"""Skill Permission Service

业务层的权限检查服务，连接数据库和框架层验证逻辑。
提供permission checker factory，供Agent运行时使用。

包含per-session权限缓存，避免每次tool call都查数据库。

[INPUT]
- myrm_agent_harness.backends.skills::SkillPermission, check_permission_for_tool_call, log_permission_usage, session_id_var (POS: 框架层技能权限映射与校验)
- app.database.connection::get_session (POS: 数据库连接管理)
- app.database.models::SkillPermissionGrant (POS: 安全域模型)

[OUTPUT]
- create_permission_checker / create_async_permission_checker: 同步/异步权限检查器工厂
- load_granted_permissions / load_granted_permissions_cached: 权限加载（含 per-session 缓存）
- clear_permission_cache: 缓存清理

[POS]
技能权限服务：桥接数据库授权与框架层权限验证，提供 per-session 缓存避免每次 tool call 查库。
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
    """创建permission checker函数（同步版本）

    供真正同步的工具执行路径使用（非事件循环线程）。
    异步 Agent 路径请使用 :func:`create_async_permission_checker`，避免
    在运行中事件循环内调用 asyncio.run 导致 RuntimeError。

    Returns:
        Permission checker函数: (skill_id, permission_type, operation) -> (allowed, reason)

    Usage:
        checker = create_permission_checker()
        allowed, reason = checker(skill_id, "file_write", "/path/to/file")
    """

    def checker(skill_id: str, permission_type: str, operation: str) -> tuple[bool, str]:
        """检查权限（同步包装）"""
        import asyncio

        # fail-fast：在运行中的事件循环内直接拒绝，避免 asyncio.run 嵌套
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            pass
        else:
            raise RuntimeError(
                "create_permission_checker() sync checker called from an async "
                "context; use create_async_permission_checker() instead"
            )

        async def _async_check() -> tuple[bool, str]:
            # 加载授予的权限（使用缓存）
            granted_perms = await load_granted_permissions_cached(skill_id)

            # 调用框架层验证
            allowed, reason = check_permission_for_tool_call(permission_type, granted_perms)

            # 记录日志（user_id 取当前会话上下文，缺失时 harness 提供 default_session）
            from myrm_agent_harness.backends.skills import session_id_var

            log_permission_usage(
                session_id_var.get(),
                skill_id,
                permission_type,
                operation,
                allowed,
                reason,
            )

            return allowed, reason

        return asyncio.run(_async_check())

    return checker


async def create_async_permission_checker() -> Callable[[str, str, str], Awaitable[tuple[bool, str]]]:
    """创建异步permission checker函数

    供 GuardrailMiddleware 异步工具路径使用（aevaluate）。

    Returns:
        Async permission checker: async (skill_id, permission_type, operation) -> (allowed, reason)
    """

    async def async_checker(skill_id: str, permission_type: str, operation: str) -> tuple[bool, str]:
        """异步检查权限"""
        # 加载授予的权限（per-session 缓存，避免每次 tool call 查库）
        granted_perms = await load_granted_permissions_cached(skill_id)

        # 调用框架层验证
        allowed, reason = check_permission_for_tool_call(permission_type, granted_perms)

        # 记录日志（user_id 取当前会话上下文，缺失时 harness 提供 default_session）
        from myrm_agent_harness.backends.skills import session_id_var

        log_permission_usage(
            session_id_var.get(),
            skill_id,
            permission_type,
            operation,
            allowed,
            reason,
        )

        return allowed, reason

    return async_checker


__all__ = [
    "load_granted_permissions",
    "create_permission_checker",
    "create_async_permission_checker",
]
