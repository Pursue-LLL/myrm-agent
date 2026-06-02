"""SQL-based Skill Quality Data Source

Business-layer implementation of SkillQualityDataSource Protocol.
Queries SkillQualityHistory ORM model and returns framework-layer SkillQualitySnapshot.

[INPUT]
- myrm_agent_harness.agent.skills.optimization.protocols.SkillQualityDataSource (POS: Framework Protocol)
- app.models.skill_optimization.SkillQualityHistory (POS: Business ORM Model)

[OUTPUT]
- SQLSkillQualityDataSource: SQL data source implementation

[POS]
Business-layer data source adapter that bridges framework Protocol and business ORM.
Implements dependency inversion: framework defines interface, business provides data.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from myrm_agent_harness.agent.skills.optimization import SkillQualitySnapshot

from app.database.models.skill_optimization import SkillQualityHistory

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

logger = logging.getLogger(__name__)


class SQLSkillQualityDataSource:
    """SQL-based implementation of SkillQualityDataSource Protocol

    Queries SkillQualityHistory table and converts ORM objects to Snapshot.
    Supports optional pre-aggregation for performance optimization.

    Design Principles:
    1. Protocol Implementation: Implements framework-defined interface
    2. Business Logic: Depends on business-layer ORM models
    3. Performance Optimized: Supports pre-aggregation tables
    4. Single Instance: No tenant_id, designed for Agent in Sandbox

    Features:
    - Efficient SQL queries with proper indexes
    - Optional pre-aggregation support (hourly/daily tables)
    - Connection pooling for concurrency
    - Local SQLite/PostgreSQL support

    Performance:
    - Raw query: O(N) where N is records count
    - Pre-aggregation: O(M) where M is aggregated groups count
    - Suitable for: 1M+ records with proper indexing

    Args:
        session_factory: AsyncSession factory for database connections

    Example:
        ```python
        from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
        from app.adapters.skill_optimization import SQLSkillQualityDataSource
        from myrm_agent_harness import UniversalAggregator

        engine = create_async_engine("sqlite+aiosqlite:///skill_quality.db")
        session_factory = async_sessionmaker(engine, expire_on_commit=False)

        data_source = SQLSkillQualityDataSource(session_factory)
        aggregator = UniversalAggregator(data_source)

        metrics = await aggregator.get_global_metrics()
        by_skill = await aggregator.aggregate_by_skill()
        ```
    """

    def __init__(self, session_factory: "async_sessionmaker[AsyncSession]"):
        """Initialize SQL data source

        Args:
            session_factory: AsyncSession factory from SQLAlchemy
        """
        self.session_factory = session_factory

    async def query_raw_records(
        self,
        skill_id: str | None = None,
        time_range_days: int = 30,
        filters: dict[str, str] | None = None,
    ) -> list[SkillQualitySnapshot]:
        """Query raw quality records from SkillQualityHistory table

        Args:
            skill_id: Optional skill filter
            time_range_days: Time window (1-365 days)
            filters: Additional filters (e.g., {"user_id": "test-user"})

        Returns:
            List of SkillQualitySnapshot sorted by recorded_at descending

        Example:
            ```python
            # Query all skills in last 7 days
            records = await source.query_raw_records(time_range_days=7)

            # Query specific skill
            records = await source.query_raw_records(
                skill_id="pdf-generator",
                time_range_days=30
            )

            # Query with user filter
            records = await source.query_raw_records(
                time_range_days=30,
                filters={"user_id": "user-123"}
            )
            ```
        """
        from sqlalchemy import and_, select

        from app.database.models.skill_optimization import SkillQualityHistory

        async with self.session_factory() as session:
            cutoff = datetime.now() - timedelta(days=time_range_days)

            conditions = [SkillQualityHistory.recorded_at >= cutoff]

            if skill_id:
                conditions.append(SkillQualityHistory.skill_id == skill_id)

            if filters and filters.get("user_id"):
                logger.debug(
                    "user_id filter ignored: SkillQualityHistory has no user_id column (%s)",
                    filters.get("user_id"),
                )

            stmt = select(SkillQualityHistory).where(and_(*conditions)).order_by(SkillQualityHistory.recorded_at.desc())

            result = await session.execute(stmt)
            rows = result.scalars().all()

            return [self._orm_to_snapshot(row) for row in rows]

    async def query_aggregated(
        self,
        group_by: str,
        time_range_days: int = 30,
        filters: dict[str, str] | None = None,
    ) -> list[dict[str, float]]:
        """Query pre-aggregated data (optional performance optimization)

        Note: Current implementation does not use pre-aggregation tables.
        Returns empty list to fallback to raw records aggregation.

        Future optimization: Create hourly/daily pre-aggregation tables
        for large-scale deployments (>1M records).

        Args:
            group_by: Grouping dimension ("skill_id" | "user_id" | "time_period")
            time_range_days: Time window
            filters: Additional filters

        Returns:
            Empty list (triggers fallback to raw records)

        Future implementation example:
            ```python
            # Query from skill_quality_hourly_agg table
            if group_by == "skill_id":
                stmt = select(
                    SkillQualityHourlyAgg.skill_id,
                    func.avg(SkillQualityHourlyAgg.avg_quality_score).label("avg_quality_score"),
                    func.sum(SkillQualityHourlyAgg.sample_count).label("sample_count"),
                    # ...
                ).where(SkillQualityHourlyAgg.hour >= cutoff).group_by(SkillQualityHourlyAgg.skill_id)

                result = await session.execute(stmt)
                return [dict(row._mapping) for row in result]
            ```
        """
        logger.debug("Pre-aggregation not implemented, returning empty list for fallback")
        return []

    @staticmethod
    def _orm_to_snapshot(row: "SkillQualityHistory") -> SkillQualitySnapshot:
        """Convert ORM object to framework-layer Snapshot

        Args:
            row: SkillQualityHistory ORM object

        Returns:
            SkillQualitySnapshot for framework layer
        """
        quality_score_json = row.quality_score or {}

        return SkillQualitySnapshot(
            id=row.id,
            skill_id=row.skill_id,
            recorded_at=row.recorded_at,
            overall_score=row.overall_score,
            success_rate=row.success_rate,
            token_efficiency=row.token_efficiency,
            execution_time=row.execution_time,
            user_satisfaction=row.user_satisfaction,
            prompt_tokens=quality_score_json.get("prompt_tokens", 0),
            completion_tokens=quality_score_json.get("completion_tokens", 0),
            total_tokens=quality_score_json.get("total_tokens", 0),
            llm_cost_usd=quality_score_json.get("llm_cost_usd", 0.0),
        )
