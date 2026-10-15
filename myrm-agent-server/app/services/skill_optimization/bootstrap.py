"""Skill optimization storage access.

[INPUT]
- app.adapters.skill_optimization.sqlalchemy_storage::SQLAlchemyStorage (POS: SkillOptimization 存储适配器)
- app.platform_utils::get_session_factory (POS: 数据库会话工厂)

[OUTPUT]
- get_skill_optimization_storage: 返回绑定当前会话工厂的 SQLAlchemyStorage

[POS]
skill_optimization 存储访问入口。供 API Depends 与 services 共用；每次调用都构造绑定当前会话工厂的实例，
因此调用方始终拿到持久化的 SQLAlchemyStorage。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import cast

from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.skill_optimization.sqlalchemy_storage import SQLAlchemyStorage


def get_skill_optimization_storage() -> SQLAlchemyStorage:
    """Return a SQLAlchemyStorage bound to the current session factory."""
    from app.platform_utils import get_session_factory

    return SQLAlchemyStorage(
        session_factory=cast(Callable[..., AsyncSession], get_session_factory()),
    )
