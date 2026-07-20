"""数据库连接管理

提供数据库会话和初始化功能。

使用方式：
    from app.database.connection import get_db, get_session, init_database
"""

import logging
from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession

from app.platform_utils import get_database_engine, get_session_factory

logger = logging.getLogger(__name__)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """获取数据库会话（依赖注入用）

    会话生命周期覆盖整个请求。``AsyncSession`` 在 ``commit``、``rollback`` 或会话结束前保持当前事务状态。

    用于 FastAPI 的依赖注入：
        @app.get("/users")
        async def get_users(db: AsyncSession = Depends(get_db)):
            ...
    """
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
        finally:
            await session.close()


@asynccontextmanager
async def get_session() -> AsyncIterator[AsyncSession]:
    """获取数据库会话（上下文管理器）

    用于 async with 语句：
        async with get_session() as session:
            result = await session.execute(...)
    """
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_database() -> None:
    """初始化数据库表、执行迁移和创建索引"""
    # Import all models to ensure they're registered with Base.metadata
    from app.database import models  # noqa: F401
    from app.database.migrations import create_indexes, run_migrations
    from app.database.models import Base
    from app.database.models import skill_optimization as _opt_models  # noqa: F401

    engine = get_database_engine()

    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables created/updated")
    except Exception as e:
        logger.error("Database table init failed: %s", e)
        raise

    # Pre-migration safety snapshot: protects against multi-step table rebuild
    # migrations (e.g. CREATE AS SELECT → DROP → RENAME) that leave the DB in
    # an inconsistent state if interrupted mid-sequence.
    # Fail-closed: abort migration if backup fails when manager is available,
    # to prevent destructive DDL without a recovery safety net.
    from app.database.backup import get_sqlite_backup_manager

    manager = get_sqlite_backup_manager()
    if manager is not None:
        try:
            manager.create_backup()
        except Exception as e:
            logger.error("Pre-migration backup failed, aborting migration: %s", e)
            raise

    try:
        await run_migrations(engine)
    except Exception as e:
        logger.error("Database migration failed: %s", e)
        raise

    from app.database.legacy_canvas_cleanup import remove_retired_canvas_data_dir

    remove_retired_canvas_data_dir()

    try:
        await create_indexes(engine)
    except Exception as e:
        logger.error("Index creation failed: %s", e)
        raise


__all__ = [
    "get_database_engine",
    "get_db",
    "get_session",
    "get_session_factory",
    "init_database",
]
