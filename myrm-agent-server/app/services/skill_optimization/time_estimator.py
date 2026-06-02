"""Task Time Estimation Service

Estimates batch optimization completion time based on historical data.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from statistics import median

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.skill_optimization import OptimizationRecord

logger = logging.getLogger(__name__)


@dataclass
class TimeEstimation:
    """Time estimation result

    Attributes:
        estimated_seconds: Estimated total time in seconds
        estimated_completion: Estimated completion timestamp
        average_time_per_task: Average time per task (seconds)
        confidence_level: Estimation confidence (0.0-1.0)
        sample_count: Number of historical records used
    """

    estimated_seconds: float
    estimated_completion: datetime
    average_time_per_task: float
    confidence_level: float
    sample_count: int


class TimeEstimator:
    """Batch optimization time estimator based on historical data"""

    MIN_SAMPLES_FOR_HIGH_CONFIDENCE = 10
    MIN_SAMPLES_FOR_MED_CONFIDENCE = 5
    DEFAULT_TIME_PER_TASK = 60.0  # 1 minute fallback

    def __init__(self, session: AsyncSession):
        self.session = session

    async def estimate_batch_time(
        self,
        skill_ids: list[str],
        max_concurrent: int = 3,
    ) -> TimeEstimation:
        """Estimate batch optimization completion time

        Args:
            skill_ids: List of skill IDs to optimize
            max_concurrent: Maximum concurrent tasks

        Returns:
            TimeEstimation: Estimated completion time and metadata
        """
        total_tasks = len(skill_ids)

        historical_times = await self._get_historical_execution_times(limit=50)

        if not historical_times:
            avg_time = self.DEFAULT_TIME_PER_TASK
            confidence = 0.0
            sample_count = 0
            logger.warning("No historical data available, using default time estimation")
        else:
            avg_time = median(historical_times)
            confidence = self._calculate_confidence(len(historical_times))
            sample_count = len(historical_times)

        parallel_batches = (total_tasks + max_concurrent - 1) // max_concurrent
        estimated_seconds = parallel_batches * avg_time

        estimated_completion = datetime.now() + timedelta(seconds=estimated_seconds)

        logger.info(
            f"Estimated batch time: {estimated_seconds:.1f}s for {total_tasks} tasks "
            f"({parallel_batches} parallel batches, avg {avg_time:.1f}s/task, "
            f"confidence {confidence:.2f}, samples {sample_count})"
        )

        return TimeEstimation(
            estimated_seconds=estimated_seconds,
            estimated_completion=estimated_completion,
            average_time_per_task=avg_time,
            confidence_level=confidence,
            sample_count=sample_count,
        )

    async def estimate_remaining_time(
        self,
        total_tasks: int,
        completed_tasks: int,
        elapsed_seconds: float,
    ) -> TimeEstimation:
        """Estimate remaining time for an ongoing batch

        Args:
            total_tasks: Total number of tasks
            completed_tasks: Number of completed tasks
            elapsed_seconds: Time elapsed so far (seconds)

        Returns:
            TimeEstimation: Estimated remaining time and completion timestamp
        """
        if completed_tasks == 0:
            return await self.estimate_batch_time(["dummy"] * total_tasks)

        avg_time_per_task = elapsed_seconds / completed_tasks
        remaining_tasks = total_tasks - completed_tasks
        estimated_remaining = avg_time_per_task * remaining_tasks

        estimated_completion = datetime.now() + timedelta(seconds=estimated_remaining)

        confidence = min(0.9, completed_tasks / total_tasks)

        logger.info(
            f"Estimated remaining time: {estimated_remaining:.1f}s for {remaining_tasks} tasks "
            f"(avg {avg_time_per_task:.1f}s/task, confidence {confidence:.2f})"
        )

        return TimeEstimation(
            estimated_seconds=estimated_remaining,
            estimated_completion=estimated_completion,
            average_time_per_task=avg_time_per_task,
            confidence_level=confidence,
            sample_count=completed_tasks,
        )

    async def _get_historical_execution_times(self, limit: int = 50) -> list[float]:
        """Get historical optimization execution times

        Args:
            limit: Maximum number of records to fetch

        Returns:
            list[float]: List of execution times in seconds
        """
        result = await self.session.execute(
            select(OptimizationRecord)
            .where(
                OptimizationRecord.status == "COMPLETED",
                OptimizationRecord.started_at.isnot(None),
                OptimizationRecord.completed_at.isnot(None),
            )
            .order_by(OptimizationRecord.completed_at.desc())
            .limit(limit)
        )
        records = result.scalars().all()

        times = []
        for record in records:
            if record.started_at and record.completed_at:
                duration = (record.completed_at - record.started_at).total_seconds()
                if duration > 0:
                    times.append(duration)

        return times

    def _calculate_confidence(self, sample_count: int) -> float:
        """Calculate estimation confidence based on sample count

        Args:
            sample_count: Number of historical samples

        Returns:
            float: Confidence level (0.0-1.0)
        """
        if sample_count >= self.MIN_SAMPLES_FOR_HIGH_CONFIDENCE:
            return 0.9
        elif sample_count >= self.MIN_SAMPLES_FOR_MED_CONFIDENCE:
            return 0.6
        elif sample_count > 0:
            return 0.3
        else:
            return 0.0
