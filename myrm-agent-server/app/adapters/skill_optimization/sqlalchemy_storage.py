"""SQLAlchemy Storage Adapter

1. 本文件的 INPUT/OUTPUT/POS 注释
2. 所属文件夹的 _ARCH.md

[INPUT]
- sqlalchemy.ext.asyncio (POS: SQLAlchemy异步引擎)
- myrm_agent_harness.agent.skills.optimization.protocols (POS: 存储协议)
- app.adapters.skill_optimization.*_repo (POS: 各Repository)

[OUTPUT]
- SQLAlchemyStorage: Protocol适配器，支持session和session_factory两种模式

[POS]
实现SkillOptimizationStorage Protocol，桥接框架层Protocol和业务层SQLAlchemy Repositories。
支持两种session管理模式：
1. 固定session（API场景，FastAPI依赖注入，生命周期由调用方管理）
2. session_factory（长生命周期组件如scheduler，每次操作创建独立session）
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.database.models.skill_optimization.ab_test_result import ABTestResultModel
    from app.database.models.skill_optimization.optimization_record import OptimizationRecord

from myrm_agent_harness.agent.skills.optimization import (
    ABTestResult,
    ABTestStatus,
    OptimizationResult,
    SkillQualityScore,
    SkillVersion,
    StorageError,
)
from sqlalchemy.ext.asyncio import AsyncSession

from .ab_test_repo import ABTestRepository
from .optimization_repo import OptimizationRepository
from .quality_repo import QualityRepository
from .snapshot_repo import SnapshotRepository

logger = logging.getLogger(__name__)


class SQLAlchemyStorage:
    """SQLAlchemy存储适配器

    实现SkillOptimizationStorage Protocol，使用SQLAlchemy repositories作为后端。
    支持两种 session 管理模式：
    - 固定session：API请求级，生命周期由调用方管理
    - session_factory：scheduler等长生命周期组件，每次操作创建独立session
    """

    def __init__(
        self,
        session: AsyncSession | None = None,
        session_factory: Callable[[], AsyncSession] | None = None,
    ) -> None:
        if session is None and session_factory is None:
            raise ValueError("Must provide either session or session_factory")

        self._fixed_session = session
        self._session_factory = session_factory

    @asynccontextmanager
    async def _get_session(self) -> AsyncIterator[AsyncSession]:
        """获取session（统一入口）

        固定session模式：直接返回，不关闭（调用方负责）
        factory模式：创建新session，操作完成后关闭
        """
        if self._fixed_session is not None:
            yield self._fixed_session
        else:
            assert self._session_factory is not None
            session = self._session_factory()
            try:
                yield session
            finally:
                await session.close()

    # ==================== OptimizationRecord ====================

    async def save_optimization_record(self, record: OptimizationResult) -> None:
        try:
            async with self._get_session() as session:
                repo = OptimizationRepository(session)
                existing = await repo.get_by_id(record.skill_id)
                if existing:
                    await repo.update_status(
                        record_id=existing.id,
                        status=record.status.value,
                    )
                else:
                    await repo.create(
                        skill_id=record.skill_id,
                        skill_type=record.skill_type.value,
                        baseline_score=_quality_score_to_dict(record.baseline_score),
                    )
        except StorageError:
            raise
        except Exception as e:
            raise StorageError(f"Failed to save optimization record: {e}") from e

    async def get_optimization_record(self, skill_id: str) -> OptimizationResult | None:
        try:
            async with self._get_session() as session:
                repo = OptimizationRepository(session)
                records = await repo.get_by_skill_id(skill_id, limit=1)
                if not records:
                    return None
                return self._convert_to_optimization_result(records[0])
        except StorageError:
            raise
        except Exception as e:
            raise StorageError(f"Failed to get optimization record: {e}") from e

    async def get_optimization_history(
        self,
        skill_id: str,
        limit: int = 10,
    ) -> list[OptimizationResult]:
        try:
            async with self._get_session() as session:
                repo = OptimizationRepository(session)
                records = await repo.get_by_skill_id(skill_id, limit)
                return [self._convert_to_optimization_result(r) for r in records]
        except StorageError:
            raise
        except Exception as e:
            raise StorageError(f"Failed to get optimization history: {e}") from e

    async def get_recent_optimizations(
        self,
        hours: int = 24,
        limit: int = 100,
    ) -> list[OptimizationResult]:
        try:
            async with self._get_session() as session:
                repo = OptimizationRepository(session)
                records = await repo.get_recent(limit)
                cutoff_time = datetime.now() - timedelta(hours=hours)
                filtered = [r for r in records if r.started_at >= cutoff_time]
                return [self._convert_to_optimization_result(r) for r in filtered]
        except StorageError:
            raise
        except Exception as e:
            raise StorageError(f"Failed to get recent optimizations: {e}") from e

    async def delete_old_optimizations(self, days: int = 90) -> int:
        try:
            async with self._get_session() as session:
                repo = OptimizationRepository(session)
                return await repo.delete_old_records(days)
        except StorageError:
            raise
        except Exception as e:
            raise StorageError(f"Failed to delete old optimizations: {e}") from e

    # ==================== ABTestResult ====================

    async def save_ab_test(self, result: ABTestResult) -> None:
        try:
            async with self._get_session() as session:
                repo = ABTestRepository(session)
                rows = await repo.get_by_skill_id(result.skill_id, limit=1)
                if rows:
                    first = rows[0]
                    await repo.update_status(
                        test_id=first.id,
                        status=result.status.value,
                        winner=result.winner,
                        candidate_score=_quality_score_to_dict(result.candidate_score),
                    )
                else:
                    await repo.create(
                        skill_id=result.skill_id,
                        baseline_version=result.baseline_version,
                        candidate_version=result.candidate_version,
                        baseline_score=_quality_score_to_dict(result.baseline_score),
                        candidate_score=_quality_score_to_dict(result.candidate_score),
                    )
        except StorageError:
            raise
        except Exception as e:
            raise StorageError(f"Failed to save A/B test: {e}") from e

    async def get_ab_test(self, skill_id: str) -> ABTestResult | None:
        try:
            async with self._get_session() as session:
                repo = ABTestRepository(session)
                tests = await repo.get_by_skill_id(skill_id)
                if not tests:
                    return None
                return self._convert_to_ab_test_result(tests[0])
        except StorageError:
            raise
        except Exception as e:
            raise StorageError(f"Failed to get A/B test: {e}") from e

    async def get_running_ab_tests(self) -> list[ABTestResult]:
        try:
            async with self._get_session() as session:
                repo = ABTestRepository(session)
                tests = await repo.get_running_tests()
                return [self._convert_to_ab_test_result(t) for t in tests]
        except StorageError:
            raise
        except Exception as e:
            raise StorageError(f"Failed to get running A/B tests: {e}") from e

    async def update_ab_test_status(
        self,
        skill_id: str,
        status: ABTestStatus,
        winner: str | None = None,
    ) -> None:
        try:
            async with self._get_session() as session:
                repo = ABTestRepository(session)
                rows = await repo.get_by_skill_id(skill_id, limit=1)
                if rows:
                    await repo.update_status(
                        test_id=rows[0].id,
                        status=status.value,
                        winner=winner,
                    )
        except StorageError:
            raise
        except Exception as e:
            raise StorageError(f"Failed to update A/B test status: {e}") from e

    async def increment_ab_test_sample_size(
        self,
        skill_id: str,
        increment: int = 1,
    ) -> int:
        try:
            async with self._get_session() as session:
                repo = ABTestRepository(session)
                return await repo.increment_sample_size(skill_id, increment)
        except StorageError:
            raise
        except Exception as e:
            raise StorageError(f"Failed to increment sample size: {e}") from e

    # ==================== SkillQualityHistory ====================

    async def save_quality_snapshot(
        self,
        skill_id: str,
        score: SkillQualityScore,
        version: int | None = None,
    ) -> None:
        try:
            async with self._get_session() as session:
                repo = QualityRepository(session)
                await repo.save_quality_snapshot(
                    skill_id=skill_id,
                    quality_score=_quality_score_to_dict(score),
                )
        except StorageError:
            raise
        except Exception as e:
            raise StorageError(f"Failed to save quality snapshot: {e}") from e

    async def get_quality_history(
        self,
        skill_id: str,
        days: int = 30,
    ) -> list[tuple[datetime, SkillQualityScore]]:
        try:
            async with self._get_session() as session:
                repo = QualityRepository(session)
                history = await repo.get_quality_history(skill_id, days)
                return [(h.recorded_at, self._convert_to_quality_score(h.quality_score)) for h in history]
        except StorageError:
            raise
        except Exception as e:
            raise StorageError(f"Failed to get quality history: {e}") from e

    async def get_latest_quality(
        self,
        skill_id: str,
    ) -> SkillQualityScore | None:
        try:
            async with self._get_session() as session:
                repo = QualityRepository(session)
                latest = await repo.get_latest_quality(skill_id)
                if not latest:
                    return None
                return self._convert_to_quality_score(latest.quality_score)
        except StorageError:
            raise
        except Exception as e:
            raise StorageError(f"Failed to get latest quality: {e}") from e

    async def get_top_skills(
        self,
        limit: int = 10,
    ) -> list[tuple[str, SkillQualityScore]]:
        try:
            async with self._get_session() as session:
                repo = QualityRepository(session)
                tops = await repo.get_top_skills(limit)
                return [(skill_id, self._convert_to_quality_score(score)) for skill_id, score in tops]
        except StorageError:
            raise
        except Exception as e:
            raise StorageError(f"Failed to get top skills: {e}") from e

    async def get_bottom_skills(
        self,
        limit: int = 10,
    ) -> list[tuple[str, SkillQualityScore]]:
        try:
            async with self._get_session() as session:
                repo = QualityRepository(session)
                bottoms = await repo.get_bottom_skills(limit)
                return [(skill_id, self._convert_to_quality_score(score)) for skill_id, score in bottoms]
        except StorageError:
            raise
        except Exception as e:
            raise StorageError(f"Failed to get bottom skills: {e}") from e

    # ==================== SkillVersion ====================

    async def save_skill_version(
        self,
        skill_id: str,
        version: int,
        content: str,
        quality_score: SkillQualityScore | None = None,
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
                    quality_score=quality_score,
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

    # ==================== Internal Methods ====================

    def _convert_to_optimization_result(self, record: "OptimizationRecord") -> OptimizationResult:
        from myrm_agent_harness.agent.skills.optimization import (
            OptimizationStatus,
            SecurityValidationResult,
            SkillType,
        )

        return OptimizationResult(
            skill_id=record.skill_id,
            skill_type=SkillType(record.skill_type),
            baseline_score=self._convert_to_quality_score(record.baseline_score),
            optimized_content=record.optimized_content or "",
            security_validation=SecurityValidationResult(passed=True, issues=[]),
            status=OptimizationStatus(record.status),
            started_at=record.started_at,
            completed_at=record.completed_at,
            error=None,
        )

    def _convert_to_ab_test_result(self, test: "ABTestResultModel") -> ABTestResult:
        return ABTestResult(
            skill_id=test.skill_id,
            baseline_version=test.baseline_version,
            candidate_version=test.candidate_version,
            baseline_score=self._convert_to_quality_score(test.baseline_score),
            candidate_score=self._convert_to_quality_score(test.candidate_score),
            sample_size=test.sample_size,
            status=ABTestStatus(test.status),
            started_at=test.started_at,
            completed_at=test.completed_at,
            winner=test.winner,
        )

    def _convert_to_quality_score(self, score_raw: object | None) -> SkillQualityScore:
        if score_raw is None:
            return SkillQualityScore(0.0, 0.0, 0.0, 0.0, 0.0)
        if isinstance(score_raw, (int, float)):
            v = float(score_raw)
            return SkillQualityScore(v, v, v, v, v)
        if not isinstance(score_raw, dict):
            return SkillQualityScore(0.0, 0.0, 0.0, 0.0, 0.0)
        d = score_raw

        def gf(key: str, default: float = 0.0) -> float:
            raw = d.get(key, default)
            if isinstance(raw, bool):
                return default
            if isinstance(raw, (int, float)):
                return float(raw)
            return default

        return SkillQualityScore(
            gf("success_rate"),
            gf("token_efficiency"),
            gf("execution_time"),
            gf("user_satisfaction"),
            gf("call_frequency"),
        )


def _quality_score_to_dict(score: SkillQualityScore) -> dict[str, float]:
    """将SkillQualityScore转换为dict（序列化用）"""
    return {
        "success_rate": score.success_rate,
        "token_efficiency": score.token_efficiency,
        "execution_time": score.execution_time,
        "user_satisfaction": score.user_satisfaction,
        "call_frequency": score.call_frequency,
        "overall_score": score.overall_score,
    }
