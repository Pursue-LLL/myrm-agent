"""SQLAlchemy Storage Adapter

1. 本文件的 INPUT/OUTPUT/POS 注释
2. 所属文件夹的 _ARCH.md

[INPUT]
- sqlalchemy.ext.asyncio (POS: SQLAlchemy异步引擎)
- myrm_agent_harness.agent.skills.optimization.protocols (POS: 存储协议)
- app.adapters.skill_optimization.snapshot_repo (POS: skill 版本 Repository)

[OUTPUT]
- SQLAlchemyStorage: Protocol适配器，每次操作从 session_factory 取独立 session

[POS]
实现SkillOptimizationStorage Protocol，桥接框架层Protocol和业务层SQLAlchemy Repositories。
每次操作创建独立 session 并在结束时关闭：长生命周期组件（skill loader）
不会因持有未关闭的 session 而占住连接池连接或读到过期快照。
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

from myrm_agent_harness.agent.skills.optimization import SkillVersion, StorageError
from sqlalchemy.ext.asyncio import AsyncSession

from .snapshot_repo import SnapshotRepository

logger = logging.getLogger(__name__)


class SQLAlchemyStorage:
    """SQLAlchemy存储适配器

    实现SkillOptimizationStorage Protocol，使用SQLAlchemy repositories作为后端。
    每次操作通过 session_factory 创建独立 session 并在结束时关闭。
    """

    def __init__(self, session_factory: Callable[[], AsyncSession]) -> None:
        self._session_factory = session_factory

    @asynccontextmanager
    async def _get_session(self) -> AsyncIterator[AsyncSession]:
        """为单次操作创建 session，结束时关闭"""
        session = self._session_factory()
        try:
            yield session
        finally:
            await session.close()

    # ==================== SkillVersion ====================

    async def save_skill_version(
        self,
        skill_id: str,
        version: int,
        content: str,
        created_by: str = "llm",
        optimization_id: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> SkillVersion:
        try:
            async with self._get_session() as session:
                repo = SnapshotRepository(session)
                return await repo.save_version(
                    skill_id=skill_id,
                    version=version,
                    content=content,
                    created_by=created_by,
                    optimization_id=optimization_id,
                    metadata=metadata,
                )
        except StorageError:
            raise
        except Exception as e:
            raise StorageError(f"Failed to save skill version: {e}") from e

    async def get_skill_version(
        self,
        skill_id: str,
        version: int,
    ) -> SkillVersion | None:
        try:
            async with self._get_session() as session:
                repo = SnapshotRepository(session)
                return await repo.get_version(skill_id, version)
        except StorageError:
            raise
        except Exception as e:
            raise StorageError(f"Failed to get skill version: {e}") from e

    async def get_active_version(
        self,
        skill_id: str,
    ) -> SkillVersion | None:
        try:
            async with self._get_session() as session:
                repo = SnapshotRepository(session)
                return await repo.get_active_version(skill_id)
        except StorageError:
            raise
        except Exception as e:
            raise StorageError(f"Failed to get active version: {e}") from e

    async def list_skill_versions(
        self,
        skill_id: str,
        limit: int = 50,
    ) -> list[SkillVersion]:
        try:
            async with self._get_session() as session:
                repo = SnapshotRepository(session)
                return await repo.list_versions(skill_id, limit)
        except StorageError:
            raise
        except Exception as e:
            raise StorageError(f"Failed to list skill versions: {e}") from e

    async def activate_version(
        self,
        skill_id: str,
        version: int,
    ) -> SkillVersion:
        try:
            async with self._get_session() as session:
                repo = SnapshotRepository(session)
                return await repo.activate_version(skill_id, version)
        except ValueError as e:
            raise StorageError(str(e)) from e
        except StorageError:
            raise
        except Exception as e:
            raise StorageError(f"Failed to activate version: {e}") from e

    async def delete_skill_versions(
        self,
        skill_id: str,
        keep_latest: int = 10,
    ) -> int:
        try:
            async with self._get_session() as session:
                repo = SnapshotRepository(session)
                return await repo.delete_versions(skill_id, keep_latest)
        except StorageError:
            raise
        except Exception as e:
            raise StorageError(f"Failed to delete skill versions: {e}") from e

    # ==================== Health Check ====================

    async def health_check(self) -> dict[str, bool | str]:
        try:
            from sqlalchemy import text

            async with self._get_session() as session:
                await session.execute(text("SELECT 1"))
                return {
                    "healthy": True,
                    "storage_type": "sqlalchemy",
                    "readable": True,
                    "writable": True,
                }
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return {
                "healthy": False,
                "storage_type": "sqlalchemy",
                "readable": False,
                "writable": False,
                "error": str(e),
            }
